import csv
import io
import re
import unicodedata

from django.core.exceptions import ValidationError

from .models import VocabWord


MAX_ROWS = 500
MAX_TEXT_LENGTH = 250000
FIELDS = ('word', 'word_type', 'meaning', 'example')
HEADER_ALIASES = {
    'word': 'word', 'vocabulary': 'word', 'tu': 'word', 'tuvung': 'word',
    'wordtype': 'word_type', 'loaitu': 'word_type', 'partofspeech': 'word_type',
    'meaning': 'meaning', 'nghia': 'meaning', 'definition': 'meaning',
    'example': 'example', 'vidu': 'example',
    'order': 'order', 'stt': 'order', 'number': 'order',
}


def word_key(value):
    return ' '.join(unicodedata.normalize('NFKC', value).casefold().split())


def header_name(value):
    value = unicodedata.normalize('NFD', value.casefold().replace('đ', 'd'))
    value = ''.join(char for char in value if not unicodedata.combining(char))
    return HEADER_ALIASES.get(re.sub(r'[\s_-]+', '', value))


def validate_vocabulary_rows(rows):
    if not isinstance(rows, list) or not rows:
        raise ValidationError('Chưa có từ vựng. Nhập mỗi từ trên một dòng hoặc tải tệp CSV/TXT.')
    if len(rows) > MAX_ROWS:
        raise ValidationError(f'Mỗi lần nhập tối đa {MAX_ROWS} từ. Chia danh sách thành các phần nhỏ hơn.')
    cleaned = []
    for index, row in enumerate(rows, 1):
        if not isinstance(row, dict) or any(not isinstance(row.get(field, ''), str) for field in FIELDS):
            raise ValidationError(f'Dòng {index}: dữ liệu từ vựng không hợp lệ.')
        values = {field: row.get(field, '').strip() for field in FIELDS}
        line = row.get('line', index)
        if not values['word']:
            raise ValidationError(f'Dòng {line}: thiếu từ vựng.')
        if len(values['example']) > 2000:
            raise ValidationError(f'Dòng {line}: ví dụ tối đa 2.000 ký tự.')
        try:
            VocabWord(**values).full_clean(exclude=['lesson'])
        except ValidationError as exc:
            raise ValidationError(f'Dòng {line}: ' + ' '.join(exc.messages)) from exc
        cleaned.append({**values, 'line': line})
    return cleaned


def parse_vocabulary_text(text, *, csv_file=False):
    text = text.lstrip('\ufeff')
    if len(text) > MAX_TEXT_LENGTH or '\x00' in text:
        raise ValidationError('Danh sách quá dài hoặc chứa ký tự không hợp lệ. Tối đa 250.000 ký tự.')
    delimiter = ',' if csv_file else None
    for line in text.splitlines():
        if not line.strip():
            continue
        try:
            candidates = [(len(next(csv.reader([line], delimiter=value))), value)
                          for value in ('\t', '|', ';', ',')]
        except csv.Error as exc:
            raise ValidationError('Có dòng quá dài hoặc sai định dạng. Kiểm tra lại cột từ, nghĩa và ví dụ.') from exc
        width = max((count for count, _ in candidates), default=1)
        if width > 1:
            delimiter = next(value for count, value in candidates if count == width)
            break
    if delimiter is None:
        raw = [(line, [value.strip()]) for line, value in enumerate(text.splitlines(), 1) if value.strip()]
    else:
        raw = []
        reader = csv.reader(io.StringIO(text), delimiter=delimiter, strict=True)
        try:
            for values in reader:
                if any(value.strip() for value in values):
                    raw.append((reader.line_num, [value.strip() for value in values]))
        except csv.Error as exc:
            raise ValidationError(f'Dòng {reader.line_num}: định dạng cột hoặc dấu nháy chưa đúng.') from exc
    if not raw:
        raise ValidationError('Danh sách chưa có từ vựng.')
    headers = [header_name(value) for value in raw[0][1]]
    if 'word' in headers and (csv_file or sum(value is not None for value in headers) > 1) and not all(headers):
        raise ValidationError('Tiêu đề có cột chưa hỗ trợ. Dùng word, word_type, meaning, example và STT nếu có.')
    has_header = ('word' in headers and all(headers) and
                  (len(headers) > 1 or csv_file))
    if has_header:
        if len(headers) != len(set(headers)):
            raise ValidationError('Tiêu đề có cột bị trùng. Mỗi cột word, word_type, meaning, example chỉ xuất hiện một lần.')
        raw = raw[1:]
    rows = []
    for line, values in raw:
        if has_header:
            if len(values) > len(headers):
                raise ValidationError(f'Dòng {line}: thừa cột so với tiêu đề. Đặt nội dung chứa dấu phân cách trong dấu nháy kép.')
            row = dict(zip(headers, values + [''] * (len(headers) - len(values))))
        else:
            if len(values) == 5 and values[0].isdigit():
                values = values[1:]
            if len(values) > 4:
                raise ValidationError(f'Dòng {line}: chỉ nhận tối đa 4 cột: từ, loại từ, nghĩa, ví dụ.')
            columns = ('word', 'meaning') if len(values) == 2 else FIELDS
            row = dict(zip(columns, values))
            if len(values) == 1:
                row['word'] = re.sub(r'^\d+[.)]\s+', '', row['word'])
        rows.append({field: row.get(field, '') for field in FIELDS} | {'line': line})
    return validate_vocabulary_rows(rows)


def vocabulary_import_plan(lesson, rows):
    existing = {word_key(word) for word in lesson.words.values_list('word', flat=True)}
    seen, preview = set(), []
    for row in rows:
        key = word_key(row['word'])
        status = 'existing' if key in existing else 'repeated' if key in seen else 'add'
        preview.append({**row, 'status': status})
        seen.add(key)
    return preview
