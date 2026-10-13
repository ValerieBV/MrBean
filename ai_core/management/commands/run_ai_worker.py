import time
from django.core.management.base import BaseCommand
from django.db import close_old_connections
from ai_core.models import GradingJob
from ai_core.services import expire_jobs, process_job


class Command(BaseCommand):
    help = 'Process durable AI queue; supervise alongside web server.'

    def add_arguments(self, parser):
        parser.add_argument('--once', action='store_true')

    def handle(self, *args, **options):
        try:
            while True:
                close_old_connections()
                expire_jobs()
                job_id = GradingJob.objects.filter(status='queued').values_list('pk', flat=True).first()
                if job_id:
                    process_job(job_id)
                if options['once']:
                    return
                if not job_id:
                    time.sleep(1)
        except KeyboardInterrupt:
            self.stdout.write('Worker stopped; interrupted jobs expire into manual queue.')
