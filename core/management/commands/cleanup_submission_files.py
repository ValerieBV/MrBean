from datetime import timedelta
import posixpath

from django.core.files.storage import default_storage
from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from core.submission_files import SUBMISSION_PREFIXES, file_is_referenced


class Command(BaseCommand):
    help = 'Liệt kê file bài nộp mồ côi; chỉ xóa khi có --delete. Bỏ qua file mới trong 24 giờ.'

    def add_arguments(self, parser):
        parser.add_argument('--delete', action='store_true', help='Xóa các file mồ côi đã liệt kê.')
        parser.add_argument('--min-age-hours', type=int, default=24)
        parser.add_argument('--database', default='default')

    def handle(self, *args, **options):
        if options['min_age_hours'] < 1:
            raise CommandError('--min-age-hours phải ít nhất là 1.')
        cutoff = timezone.now() - timedelta(hours=options['min_age_hours'])
        candidates = removed = 0
        for prefix in SUBMISSION_PREFIXES:
            for name in self.files_under(prefix.rstrip('/')):
                if file_is_referenced(name, options['database']):
                    continue
                try:
                    modified = default_storage.get_modified_time(name)
                    if timezone.is_naive(modified):
                        modified = timezone.make_aware(modified)
                    if modified > cutoff:
                        continue
                    candidates += 1
                    if options['delete']:
                        default_storage.delete(name)
                        removed += 1
                    self.stdout.write(name)
                except (OSError, NotImplementedError) as exc:
                    self.stderr.write(f'Bỏ qua {name}: {exc}')
        self.stdout.write(f'File mồ côi: {candidates}; đã xóa: {removed}.')

    def files_under(self, directory):
        try:
            folders, files = default_storage.listdir(directory)
        except FileNotFoundError:
            return
        for name in files:
            yield posixpath.join(directory, name)
        for folder in folders:
            yield from self.files_under(posixpath.join(directory, folder))
