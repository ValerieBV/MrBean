"""Structured Word answer explanations, with one passage per three questions."""
import io
import re
import unicodedata
import zipfile
from html import escape

from django.core.exceptions import ValidationError
from .docx_import import read_docx_records
from .listening import FIRST_NUMBER, LISTENING_SPECS
from .question_import import QUESTION, OPTION

GROUP = re.compile(r'^(?:(?:đoạn(?:\s+hội\s+thoại|\s+nói)?|nhóm(?:\s+câu)?|câu|questions?|group)\s*)?(\d+)\s*(?:[–—-]|to|through)\s*(\d+)\s*[:.]?\s*$', re.I)
ANSWER = re.compile(r'^(?:đáp\s*án(?:\s*đúng)?|answer|correct(?:\s*answer)?)\s*[:：]\s*\(?([A-D])\)?(?:\s*[.):-])?\s*(.*)$', re.I)
EXPLANATION = re.compile(r'^(?:giải\s*thích|lời\s*giải|explanation|reason)\s*[:：]\s*(.*)$', re.I)
SCRIPT = re.compile(r'^(?:hội\s*thoại|đoạn\s*hội\s*thoại|bài\s*nói|đoạn\s*nói|nội\s*dung|transcript|script|passage)\s*[:：]\s*(.*)$', re.I)
TRANSLATION = re.compile(r'^(?:bản\s*dịch|dịch|translation)\s*[:：]\s*(.*)$', re.I)
PROMPT = re.compile(r'^(?:câu\s*hỏi|question)\s*[:：]\s*(.*)$', re.I)
PART_HEADER = re.compile(r'^(?:PART|DẠNG)\s*([1-4])(?:\s*[:.–—-]\s*.*|\s+.*)?$', re.I)


def _clean(value, maximum, label):
    if not isinstance(value, str) or len(value) > maximum:
        raise ValidationError(f'{label}: nội dung không hợp lệ hoặc quá dài.')
    return unicodedata.normalize('NFKC', value).replace('\r\n', '\n').replace('\r', '\n').strip()


def normalize_solutions(value, kind, *, expected_numbers=None):
    spec = LISTENING_SPECS.get(kind)
    if not spec or kind == 'legacy' or not isinstance(value, dict):
        raise ValidationError('Dạng bài hoặc nội dung lời giải không hợp lệ.')
    rows, passages = value.get('questions'), value.get('passages', [])
    count = spec['count']
    if not isinstance(rows, list) or len(rows) != count or not isinstance(passages, list):
        raise ValidationError(f'Cần đủ đáp án và giải thích cho {count} câu.')
    clean, seen = [], set()
    for row in rows:
        if not isinstance(row, dict) or type(row.get('number')) is not int or not 1 <= row['number'] <= 9999:
            raise ValidationError('Mỗi lời giải cần có số câu hợp lệ.')
        n = row['number']
        if n in seen:
            raise ValidationError(f'Câu {n} bị trùng trong lời giải.')
        seen.add(n)
        answer = _clean(row.get('answer', ''), 1, f'Câu {n}').upper()
        if answer not in spec['choices'] or not answer:
            raise ValidationError(f'Câu {n}: cần đáp án {" / ".join(spec["choices"])}.')
        explanation = _clean(row.get('explanation', ''), 10000, f'Giải thích câu {n}')
        if not explanation:
            raise ValidationError(f'Câu {n}: chưa có giải thích đáp án.')
        question = {'number': n, 'answer': answer, 'explanation': explanation,
            'question_text': _clean(row.get('question_text', ''), 10000, f'Câu hỏi {n}'),
            'translation': _clean(row.get('translation', ''), 10000, f'Bản dịch câu {n}')}
        for letter in spec['choices']:
            key = 'option_' + letter.lower()
            question[key] = _clean(row.get(key, ''), 255, f'Lựa chọn {letter} câu {n}')
            if kind != 'part1' and not question[key]:
                raise ValidationError(f'Câu {n}: thiếu nội dung lựa chọn {letter}.')
        if kind != 'part1' and not question['question_text']:
            raise ValidationError(f'Câu {n}: thiếu nội dung câu hỏi.')
        clean.append(question)
    clean.sort(key=lambda row: row['number'])
    submitted = [row['number'] for row in clean]
    default = list(range(FIRST_NUMBER[kind], FIRST_NUMBER[kind]+count))
    numbers = expected_numbers or default
    mapping = dict(zip(range(1, count+1), numbers)) if submitted == list(range(1, count+1)) else {}
    if mapping:
        for row in clean:
            row['number'] = mapping[row['number']]
    if [row['number'] for row in clean] != numbers:
        raise ValidationError('Số câu trong lời giải không khớp với bài nghe đã chọn.')
    groups = []
    if kind in ('part3', 'part4'):
        if len(passages) != count//3:
            raise ValidationError(f'Cần {count//3} đoạn, mỗi đoạn dùng chung cho đúng 3 câu hỏi.')
        for passage in passages:
            if not isinstance(passage, dict) or type(passage.get('start')) is not int or type(passage.get('end')) is not int:
                raise ValidationError('Mỗi đoạn cần ghi rõ phạm vi câu, ví dụ Đoạn 32–34.')
            start, end = passage['start'], passage['end']
            start, end = mapping.get(start, start), mapping.get(end, end)
            text = _clean(passage.get('text', ''), 20000, f'Đoạn {start}–{end}')
            if not text:
                raise ValidationError(f'Đoạn {start}–{end}: chưa có nội dung nghe.')
            groups.append({'start': start, 'end': end, 'text': text,
                'translation': _clean(passage.get('translation', ''), 20000, f'Bản dịch đoạn {start}–{end}')})
        groups.sort(key=lambda row: row['start'])
        if [(g['start'], g['end']) for g in groups] != [(numbers[i], numbers[i+2]) for i in range(0, count, 3)]:
            raise ValidationError('Phạm vi đoạn bị trùng, thiếu hoặc không khớp nhóm 3 câu của bài nghe.')
    elif passages:
        raise ValidationError('Dạng 1 và dạng 2 không dùng đoạn chung cho nhóm 3 câu.')
    return {'version': 1, 'kind': kind, 'questions': clean, 'passages': groups}


def extract_docx_solutions(upload, kind):
    questions, passages, question, passage, field = [], [], None, None, None
    records = read_docx_records(upload)
    if any(PART_HEADER.match(row['text'].strip()) for row in records):
        selected, current = [], None
        for record in records:
            header = PART_HEADER.match(record['text'].strip())
            if header:
                current = 'part' + header[1]
            elif current == kind:
                selected.append(record)
        records = selected
    for record in records:
        line = unicodedata.normalize('NFKC', record['text']).replace('\u200b', '').strip()
        if not line or re.match(r'^(?:PART\s*\d|DẠNG\s*\d|ĐÁP ÁN VÀ GIẢI THÍCH)\s*$', line, re.I):
            continue
        group = GROUP.match(line)
        if group:
            passage = {'start': int(group[1]), 'end': int(group[2]), 'text': '', 'translation': ''}
            passages.append(passage)
            question, field = None, 'passage_text'
            continue
        match = QUESTION.match(line)
        if match:
            question = {'number': int(match[1]), 'question_text': '', 'answer': '', 'explanation': '', 'translation': ''}
            questions.append(question)
            field, line = 'question_text', match[2]
        answer = ANSWER.match(line)
        if answer and question is not None:
            chosen = answer[1].upper()
            if question['answer'] and question['answer'] != chosen:
                raise ValidationError(f'Câu {question["number"]}: có nhiều đáp án đúng khác nhau.')
            question['answer'], field = chosen, None
            continue
        explain = EXPLANATION.match(line)
        if explain and question is not None:
            field, line = 'explanation', explain[1]
        else:
            translation = TRANSLATION.match(line)
            script = SCRIPT.match(line)
            prompt = PROMPT.match(line)
            if translation:
                field, line = ('translation' if question is not None else 'passage_translation'), translation[1]
            elif script and passage is not None and question is None:
                field, line = 'passage_text', script[1]
            elif prompt and question is not None:
                field, line = 'question_text', prompt[1]
            elif question is not None and field != 'explanation':
                options = list(OPTION.finditer(line))
                if options:
                    before = line[:options[0].start()].strip()
                    if before and field:
                        question[field] = (question.get(field, '') + '\n' + before).strip()
                    for index, option in enumerate(options):
                        letter = (option[1] or option[2]).upper()
                        field = 'option_' + letter.lower()
                        end = options[index+1].start() if index+1 < len(options) else len(line)
                        question[field] = (question.get(field, '') + ' ' + line[option.end():end]).strip()
                        if record['bold'] and len(options) == 1:
                            if question['answer'] and question['answer'] != letter:
                                raise ValidationError(f'Câu {question["number"]}: lựa chọn in đậm không khớp đáp án.')
                            question['answer'] = letter
                    continue
        if field and field.startswith('passage_') and passage is not None:
            key = field.removeprefix('passage_')
            passage[key] = (passage[key] + '\n' + line).strip()
        elif field and question is not None:
            question[field] = (question.get(field, '') + '\n' + line).strip()
    return normalize_solutions({'questions': questions, 'passages': passages}, kind)


def solution_question_content(bundle):
    return [{key: row.get(key, '') for key in ('number', 'question_text', 'option_a', 'option_b', 'option_c', 'option_d')}
            for row in bundle['questions']]


def match_solutions_to_questions(bundle, questions, kind):
    for row, question in zip(bundle['questions'], questions):
        if row['answer'] != question.correct_option:
            raise ValidationError(f'Câu {row["number"]}: đáp án trong lời giải khác bảng đáp án đã giao.')
        if kind in ('part3', 'part4') and any(
                re.sub(r'\s+', ' ', row.get(key, '')).strip() != re.sub(r'\s+', ' ', getattr(question, key)).strip()
                for key in ('question_text', 'option_a', 'option_b', 'option_c', 'option_d')):
            raise ValidationError(f'Câu {row["number"]}: nội dung câu hỏi hoặc lựa chọn không khớp đề đã giao.')


def solution_template(kind):
    """An editable, unfilled DOCX structure; no sample answers are invented."""
    spec = LISTENING_SPECS[kind]
    paragraphs = [f'DẠNG {int(kind[-1])}']
    start = FIRST_NUMBER[kind]
    for index in range(spec['count']):
        n = start+index
        if kind in ('part3', 'part4') and index % 3 == 0:
            paragraphs.extend([f'Đoạn {n}–{n+2}', 'Nội dung:', 'Bản dịch:'])
        paragraphs.append(f'{n}.')
        paragraphs.extend(f'({letter})' for letter in spec['choices'])
        paragraphs.extend(['Đáp án:', 'Giải thích:'])
    body = ''.join('<w:p><w:r><w:t xml:space="preserve">'+escape(text)+'</w:t></w:r></w:p>' for text in paragraphs)
    output = io.BytesIO()
    with zipfile.ZipFile(output, 'w', zipfile.ZIP_DEFLATED) as archive:
        archive.writestr('[Content_Types].xml', '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"><Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/><Default Extension="xml" ContentType="application/xml"/><Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/></Types>')
        archive.writestr('_rels/.rels', '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/></Relationships>')
        archive.writestr('word/document.xml', '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"><w:body>'+body+'<w:sectPr><w:pgSz w:w="11906" w:h="16838"/><w:pgMar w:top="1134" w:right="1134" w:bottom="1134" w:left="1134"/></w:sectPr></w:body></w:document>')
    return output.getvalue()
