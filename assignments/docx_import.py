"""Read question text from DOCX without opening Word or executing document content."""
import io
import re
import zipfile
from pathlib import Path
from xml.etree import ElementTree as ET
from django.core.exceptions import ValidationError
from .question_import import QUESTION, parse_lines, select_questions

MAX_UPLOAD = 10 * 1024 * 1024


def _name(tag):
    return tag.rsplit('}', 1)[-1]


def _attr(node, key, default=None):
    if node is None:
        return default
    return next((value for name, value in node.attrib.items() if _name(name) == key), default)


def _part(archive, path, limit, required=False):
    try:
        info = archive.getinfo(path)
    except KeyError:
        if required:
            raise ValidationError('File Word không có nội dung DOCX hợp lệ.') from None
        return None
    if info.file_size > limit:
        raise ValidationError('Nội dung Word quá lớn. Tách riêng phần đề cần dùng.')
    with archive.open(info) as stream:
        data = stream.read(limit + 1)
    if len(data) > limit or re.search(br'<!\s*(?:DOCTYPE|ENTITY)\b', data, re.I):
        raise ValidationError('Cấu trúc file Word không được hỗ trợ. Lưu lại dưới dạng .docx.')
    return ET.fromstring(data)


class _Numbering:
    def __init__(self, numbering, styles):
        self.levels, self.counters, self.styles = {}, {}, {}
        if styles is not None:
            self.styles = {_attr(style, 'styleId'): style for style in styles.findall('./{*}style')}
        if numbering is None:
            return
        abstracts = {_attr(node, 'abstractNumId'): node for node in numbering.findall('./{*}abstractNum')}
        for instance in numbering.findall('./{*}num'):
            abstract = abstracts.get(_attr(instance.find('./{*}abstractNumId'), 'val'))
            if abstract is None:
                continue
            levels = {int(_attr(level, 'ilvl', '0')): level for level in abstract.findall('./{*}lvl')}
            overrides = {int(_attr(level, 'ilvl', '0')): level for level in instance.findall('./{*}lvlOverride')}
            self.levels[_attr(instance, 'numId')] = {}
            for index, level in levels.items():
                override = overrides.get(index)
                replacement = override.find('./{*}lvl') if override is not None else None
                if replacement is not None:
                    level = replacement
                start = _attr(level.find('./{*}start'), 'val', '1')
                if override is not None:
                    start = _attr(override.find('./{*}startOverride'), 'val', start)
                self.levels[_attr(instance, 'numId')][index] = {
                    'start': int(start), 'format': _attr(level.find('./{*}numFmt'), 'val', 'decimal'),
                    'text': _attr(level.find('./{*}lvlText'), 'val', f'%{index+1}.')}

    def _properties(self, paragraph):
        values = {}
        props = paragraph.find('./{*}pPr/{*}numPr')
        style_id = _attr(paragraph.find('./{*}pPr/{*}pStyle'), 'val')
        seen = set()
        while True:
            if props is not None:
                for key in ('numId', 'ilvl'):
                    value = _attr(props.find('./{*}'+key), 'val')
                    if value is not None:
                        values.setdefault(key, value)
            if style_id not in self.styles or style_id in seen:
                return values
            seen.add(style_id)
            style = self.styles[style_id]
            props = style.find('./{*}pPr/{*}numPr')
            style_id = _attr(style.find('./{*}basedOn'), 'val')

    @staticmethod
    def _format(number, fmt):
        if fmt in ('upperLetter', 'lowerLetter'):
            letters = ''
            while number > 0:
                number, remainder = divmod(number-1, 26)
                letters = chr(65+remainder) + letters
            return letters if fmt == 'upperLetter' else letters.lower()
        return str(number)

    def prefix(self, paragraph):
        props = self._properties(paragraph)
        number_id = props.get('numId')
        level_index = int(props.get('ilvl', '0'))
        levels = self.levels.get(number_id, {})
        definition = levels.get(level_index)
        if not definition or definition['format'] not in ('decimal', 'decimalZero', 'upperLetter', 'lowerLetter'):
            return ''
        counters = self.counters.setdefault(number_id, {})
        counters[level_index] = counters.get(level_index, definition['start']-1) + 1
        for index in list(counters):
            if index > level_index:
                del counters[index]
        return re.sub(r'%([1-9])', lambda match: self._format(
            counters.get(int(match[1])-1, levels.get(int(match[1])-1, {}).get('start', 1)),
            levels.get(int(match[1])-1, {}).get('format', 'decimal')), definition['text'])


def _text(paragraph):
    pieces = []
    for element in paragraph.iter():
        tag = _name(element.tag)
        if tag == 't':
            pieces.append(element.text or '')
        elif tag == 'tab':
            pieces.append('\t')
        elif tag in ('br', 'cr'):
            pieces.append('\n')
    return ''.join(pieces)


def _paragraphs(block):
    for child in block:
        tag = _name(child.tag)
        if tag == 'p':
            yield child
        elif tag == 'tbl':
            rows = [row.findall('./{*}tc') for row in child.findall('./{*}tr')]
            # Layout tables with printed question numbers must be read down each column.
            two_columns = rows and all(len(row) == 2 for row in rows) and all(
                any(QUESTION.match(_text(p).strip()) for row in rows for p in row[column].iterfind('.//{*}p'))
                for column in (0, 1))
            cells = [row[column] for column in (0, 1) for row in rows] if two_columns else [cell for row in rows for cell in row]
            for cell in cells:
                yield from _paragraphs(cell)
        elif tag in ('sdt', 'sdtContent'):
            yield from _paragraphs(child)


def extract_docx_questions(upload, kind):
    if kind not in ('part3', 'part4'):
        raise ValidationError('Nhập Word chỉ dùng cho dạng 3 và dạng 4.')
    if Path(upload.name).suffix.lower() != '.docx' or not 0 < upload.size <= MAX_UPLOAD:
        raise ValidationError('Chọn file Word .docx tối đa 10 MiB. Với .doc, lưu lại thành .docx.')
    upload.seek(0)
    data = upload.read(MAX_UPLOAD + 1)
    if len(data) > MAX_UPLOAD:
        raise ValidationError('File Word tối đa 10 MiB.')
    try:
        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            if len(archive.infolist()) > 1000:
                raise ValidationError('File Word có quá nhiều thành phần. Tách riêng phần đề cần dùng.')
            document = _part(archive, 'word/document.xml', 8*1024*1024, required=True)
            numbering = _Numbering(_part(archive, 'word/numbering.xml', 1024*1024),
                                   _part(archive, 'word/styles.xml', 2*1024*1024))
            body = document.find('./{*}body')
            if body is None:
                raise ValidationError('Không tìm thấy nội dung trong file Word.')
            lines, characters = [], 0
            for paragraph in _paragraphs(body):
                text = _text(paragraph).strip()
                prefix = numbering.prefix(paragraph)
                if prefix and not QUESTION.match(text) and not re.match(r'^\s*[(（]?[A-D][)）.:]', text, re.I):
                    text = prefix+' '+text
                characters += len(text)
                if characters > 250000 or len(lines) > 40000:
                    raise ValidationError('Word quá nhiều nội dung. Tách riêng phần đề cần dùng.')
                lines.extend(text.splitlines())
    except (zipfile.BadZipFile, ET.ParseError, RuntimeError, ValueError, KeyError, OverflowError):
        raise ValidationError('Không đọc được file Word. Mở tài liệu và lưu lại dưới dạng .docx.') from None
    if not any(line.strip() for line in lines):
        raise ValidationError('Word không có văn bản đọc được. Nếu chỉ chứa ảnh, xuất PDF rồi dùng “Đọc bản scan bằng AI”.')
    questions = select_questions(parse_lines(lines), kind)
    if not questions:
        raise ValidationError('Chưa tách được câu hỏi trong Word. Dùng số câu như 32. hoặc 71. và các lựa chọn A., B., C., D.')
    return questions
