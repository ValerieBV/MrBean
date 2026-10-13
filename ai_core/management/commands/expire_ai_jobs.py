from django.core.management.base import BaseCommand
from ai_core.services import expire_jobs


class Command(BaseCommand):
    help = 'Move jobs older than five minutes to manual queue; run every minute independently of workers.'

    def handle(self, *args, **options):
        self.stdout.write(str(expire_jobs()))
