"""Authenticated views may use this response after resolving their permitted file."""
import re
from django.http import FileResponse, HttpResponse, StreamingHttpResponse


def private_media_response(stream, request=None):
    """Support one byte range so browser players can seek without downloading all bytes."""
    try:
        stream.seek(0, 2)
        size = stream.tell()
        stream.seek(0)
    except (AttributeError, OSError):
        response = FileResponse(stream)
        response['Cache-Control'] = 'private, no-store'
        response['X-Content-Type-Options'] = 'nosniff'
        return response
    response = FileResponse(stream)
    response['Accept-Ranges'] = 'bytes'
    response['Cache-Control'] = 'private, no-store'
    response['X-Content-Type-Options'] = 'nosniff'
    header = request.headers.get('Range', '') if request is not None else ''
    if not header or request.headers.get('If-Range'):
        return response
    try:
        match = re.fullmatch(r'bytes=(\d*)-(\d*)', header) if len(header) <= 150 else None
        if not match or not any(match.groups()) or not size:
            raise ValueError()
        first, last = match.groups()
        if first:
            start, end = int(first), min(int(last), size-1) if last else size-1
        else:
            suffix = int(last)
            if suffix <= 0:
                raise ValueError()
            start, end = max(0, size-suffix), size-1
        if not 0 <= start <= end < size:
            raise ValueError()
    except ValueError:
        stream.close()
        rejected = HttpResponse(status=416)
        rejected['Content-Range'] = f'bytes */{size}'
        rejected['Accept-Ranges'] = 'bytes'
        rejected['Cache-Control'] = 'private, no-store'
        return rejected
    stream.seek(start)
    def chunks():
        remaining = end-start+1
        try:
            while remaining:
                data = stream.read(min(65536, remaining))
                if not data:
                    return
                remaining -= len(data)
                yield data
        finally:
            stream.close()
    partial = StreamingHttpResponse(chunks(), status=206, content_type=response['Content-Type'])
    partial._resource_closers.append(stream.close)
    partial['Content-Length'] = str(end-start+1)
    partial['Content-Range'] = f'bytes {start}-{end}/{size}'
    partial['Accept-Ranges'] = 'bytes'
    partial['Cache-Control'] = 'private, no-store'
    partial['X-Content-Type-Options'] = 'nosniff'
    if 'Content-Disposition' in response:
        partial['Content-Disposition'] = response['Content-Disposition']
    return partial
