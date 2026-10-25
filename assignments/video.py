import re
from urllib.parse import urlparse, parse_qs
from django.core.exceptions import ValidationError


def youtube_embed(url):
    try:
        parsed=urlparse(url or '')
        port=parsed.port
    except ValueError as exc:
        raise ValidationError('URL video không hợp lệ.') from exc
    if parsed.scheme!='https':
        raise ValidationError('Video cần là URL HTTPS của YouTube.')
    host=(parsed.hostname or '').lower()
    if parsed.username or parsed.password or port not in (None,443):
        raise ValidationError('URL video không hợp lệ.')
    parts=parsed.path.strip('/').split('/')
    if host=='youtu.be':
        video_id=parts[0]
    elif host in ('youtube.com','www.youtube.com','m.youtube.com'):
        video_id=(parse_qs(parsed.query).get('v') or [''])[0] if parsed.path=='/watch' else (parts[1] if len(parts)==2 and parts[0] in ('embed','shorts') else '')
    else:
        raise ValidationError('Chỉ nhúng video từ YouTube; không dùng URL ngoài danh sách cho phép.')
    if not re.fullmatch(r'[A-Za-z0-9_-]{11}',video_id):
        raise ValidationError('Không nhận diện được mã video YouTube.')
    return 'https://www.youtube-nocookie.com/embed/'+video_id
