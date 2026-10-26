import time
from django.core.management.base import BaseCommand
from django.db import close_old_connections
from ai_core.services import expire_jobs


class Command(BaseCommand):
    help = 'Chuyển bài vượt 300 giây sang chấm thủ công. Chạy --loop độc lập với worker.'

    def add_arguments(self,parser):
        parser.add_argument('--loop',action='store_true',help='Giữ watchdog chạy liên tục, kiểm tra mỗi giây')

    def handle(self,*args,**options):
        try:
            while True:
                close_old_connections()
                count=expire_jobs()
                if count or not options['loop']:self.stdout.write(str(count))
                if not options['loop']:return
                time.sleep(1)
        except KeyboardInterrupt:
            self.stdout.write('Watchdog stopped.')
