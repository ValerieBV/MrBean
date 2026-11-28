from django.conf import settings
from django.core.management.base import BaseCommand, CommandError


class Command(BaseCommand):
    help = 'Kiểm tra cấu hình key; --live gửi một yêu cầu OpenAI nhỏ có thể phát sinh phí.'

    def add_arguments(self, parser):
        parser.add_argument('--live', action='store_true')

    def handle(self, *args, **options):
        self.stdout.write(f'Model chấm: {settings.OPENAI_TEXT_MODEL}; transcript: {settings.OPENAI_TRANSCRIBE_MODEL}')
        if not settings.OPENAI_API_KEY:
            raise CommandError('Chưa có OPENAI_API_KEY. Đặt trong .env hoặc biến môi trường, rồi khởi động lại worker.')
        self.stdout.write('Đã có API key (không hiển thị giá trị).')
        if not options['live']:
            self.stdout.write('Chưa gọi API. Thêm --live để thử kết nối; có thể phát sinh phí.')
            return
        import openai
        try:
            with openai.OpenAI(api_key=settings.OPENAI_API_KEY, timeout=20, max_retries=0) as client:
                response=client.responses.create(model=settings.OPENAI_TEXT_MODEL, input='Reply with OK.',store=False)
            if not response.output_text:
                raise CommandError('API phản hồi nhưng không có văn bản.')
        except openai.AuthenticationError:
            raise CommandError('Key không hợp lệ hoặc đã bị thu hồi.') from None
        except openai.RateLimitError:
            raise CommandError('Vượt rate limit hoặc hết hạn mức API; kiểm tra Billing/Usage trên OpenAI Platform.') from None
        except openai.APIConnectionError:
            raise CommandError('Không kết nối được OpenAI; kiểm tra mạng/proxy.') from None
        except openai.APIError as exc:
            raise CommandError('OpenAI chưa xử lý được yêu cầu: '+type(exc).__name__+'; kiểm tra model và quyền dự án.') from None
        self.stdout.write(self.style.SUCCESS('Kết nối OpenAI thành công. Không gửi dữ liệu học viên trong phép thử này.'))
