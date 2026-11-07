"""Listening material validation and bulk answer-key parsing."""
import csv
import io
import re
import unicodedata
from pathlib import Path
from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import UploadedFile


LISTENING_SPECS = {
    'part1': {'label': 'Mô tả tranh', 'count': 6, 'choices': 'ABCD'},
    'part2': {'label': 'Hỏi - Đáp', 'count': 25, 'choices': 'ABC'},
    'part3': {'label': 'Cuộc hội thoại ngắn', 'count': 39, 'choices': 'ABCD'},
    'part4': {'label': 'Bài nói ngắn', 'count': 30, 'choices': 'ABCD'},
    'legacy': {'label': 'Bài nghe đã có', 'count': None, 'choices': 'ABCD'},
}


def validate_listening_audio(value):
    if hasattr(value, '_committed') and not value._committed:
        value = value.file
    if isinstance(value, UploadedFile):
        if not 0 < value.size <= 50 * 1024 * 1024 or Path(value.name).suffix.lower() not in (
                '.mp3', '.wav', '.m4a', '.mp4', '.ogg', '.webm'):
            raise ValidationError('File nghe phải là MP3/WAV/M4A/MP4/OGG/WebM, tối đa 50 MiB.')


def validate_listening_pdf(value):
    if hasattr(value, '_committed') and not value._committed:
        value = value.file
    if not isinstance(value, UploadedFile):
        return
    position = value.tell()
    header = value.read(5)
    value.seek(position)
    if not 0 < value.size <= 25 * 1024 * 1024 or Path(value.name).suffix.lower() != '.pdf' or header != b'%PDF-':
        raise ValidationError('Tài liệu phải là file PDF hợp lệ, tối đa 25 MiB.')


def _header(value):
    value = unicodedata.normalize('NFKD', value.casefold()).replace('đ', 'd')
    return re.sub(r'[^a-z0-9]', '', ''.join(c for c in value if not unicodedata.combining(c)))


def parse_answer_key(text, question_count, choices):
    """Accept numbered keys, a sequence of letters, or a UTF-8 CSV with a header.

    Optional CSV columns: number,answer,question_text,A,B,C,D. No guesswork:
    duplicates, gaps, out-of-range numbers and type-2 D answers are errors.
    """
    text = text.lstrip('\ufeff').strip()
    if not text or len(text) > 100000:
        raise ValidationError('Cần bảng đáp án, tối đa 100.000 ký tự.')
    rows = []
    first_line = text.splitlines()[0]
    delimiter = ';' if first_line.count(';') > first_line.count(',') else ','
    parsed = list(csv.reader(io.StringIO(text), delimiter=delimiter))
    headers = [_header(x) for x in parsed[0]] if parsed else []
    number_aliases = {'number', 'question', 'questionnumber', 'no', 'order', 'cau', 'socau', 'stt'}
    answer_aliases = {'answer', 'correctoption', 'correctanswer', 'key', 'dapan', 'dapandung'}
    number_index = next((i for i, h in enumerate(headers) if h in number_aliases), None)
    answer_index = next((i for i, h in enumerate(headers) if h in answer_aliases), None)
    if number_index is not None and answer_index is not None:
        for line, values in enumerate(parsed[1:], 2):
            if not any(v.strip() for v in values):
                continue
            if len(values) != len(headers):
                raise ValidationError(f'Dòng CSV {line} không đúng số cột. Đặt nội dung có dấu phẩy trong dấu nháy.')
            try:
                number = int(values[number_index].strip())
            except ValueError:
                raise ValidationError(f'Dòng CSV {line}: số câu không hợp lệ.') from None
            row = {'number': number, 'answer': values[answer_index].strip().upper()}
            for i, h in enumerate(headers):
                if h in ('questiontext', 'questioncontent', 'noidung'):
                    row['question_text'] = values[i].strip()
                for letter in 'ABCD':
                    if h in (letter.lower(), 'option' + letter.lower()):
                        row['option_' + letter.lower()] = values[i].strip()
            rows.append(row)
    else:
        compact = re.sub(r'[\s,;|]+', '', text).upper()
        if re.fullmatch(r'[A-D]+', compact):
            rows = [{'number': i, 'answer': answer} for i, answer in enumerate(compact, 1)]
        else:
            pattern = r'(\d+)\s*[.:\-),;]?\s*([A-D])(?=$|[\s,;|])'
            upper = text.upper()
            matches = list(re.finditer(pattern, upper))
            leftover = re.sub(pattern, '', upper)
            if not matches or re.sub(r'[\s,;|]+', '', leftover):
                raise ValidationError('Dùng dạng 1.A 2.C 3.B, chuỗi A C B, hoặc CSV có cột number,answer.')
            rows = [{'number': int(m[1]), 'answer': m[2]} for m in matches]
    by_number = {}
    for row in rows:
        number = row['number']
        if number in by_number:
            raise ValidationError(f'Câu {number} xuất hiện nhiều lần trong bảng đáp án.')
        if not 1 <= number <= question_count:
            raise ValidationError(f'Câu {number} nằm ngoài phạm vi 1–{question_count}.')
        if len(row['answer']) != 1 or row['answer'] not in choices:
            raise ValidationError(f'Câu {number}: chỉ nhận đáp án {", ".join(choices)}.')
        if len(row.get('question_text', '')) > 10000 or any(
                len(row.get('option_' + c.lower(), '')) > 255 for c in 'ABCD'):
            raise ValidationError(f'Câu {number}: nội dung hoặc lựa chọn quá dài.')
        by_number[number] = row
    missing = sorted(set(range(1, question_count + 1)) - set(by_number))
    if missing:
        raise ValidationError('Thiếu đáp án câu: ' + ', '.join(map(str, missing[:30])) + '.')
    return [by_number[n] for n in range(1, question_count + 1)]
