"""Explicit local sample data, based on A's courses and B's lesson fixtures."""
from datetime import timedelta
from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone
from accounts.models import CustomUser
from courses.models import Course, ClassRoom, Enrollment
from assignments.models import Lesson, ListeningQuestion, SpeakingTask, VocabWord, ClassAssignment
from assignments.services import assign_to_class
from dashboard.integration import sync_class_assignment


class Command(BaseCommand):
    help = 'Tạo mẫu local cho admin, giáo viên, học viên. Không sửa mật khẩu tài khoản đã tồn tại.'

    def add_arguments(self, parser):
        parser.add_argument('--password', required=True, help='Mật khẩu cho các tài khoản demo mới')

    @transaction.atomic
    def handle(self, *args, **options):
        if not settings.DEBUG:
            raise CommandError('Chỉ tạo dữ liệu mẫu khi DEBUG=True.')
        if len(options['password']) < 10:
            raise CommandError('Mật khẩu demo tối thiểu 10 ký tự.')
        users = {}
        for username, role, label in [('demo_admin','admin','Quản trị demo'),('demo_manager','manager','Quản lý demo'),
                                      ('demo_teacher','teacher','Giáo viên demo'),('demo_student','student','Học viên demo'),('demo_student2','student','Học viên chưa nộp')]:
            user, created = CustomUser.objects.get_or_create(username=username, defaults={'role':role, 'first_name':label})
            if user.role != role:
                raise CommandError('Tài khoản demo trùng tên nhưng khác vai trò; dừng để không thay đổi dữ liệu.')
            if created:
                user.set_password(options['password']); user.save()
            users[role] = user if role != 'student' or 'student' not in users else users['student']
        course, _ = Course.objects.get_or_create(code='DEMO-TOEIC', defaults={'name':'Khóa TOEIC mẫu','course_type':'TOEIC'})
        classroom, _ = ClassRoom.objects.get_or_create(class_code='DEMO-01', defaults={'name':'Lớp Mr Bean mẫu','course':course,'teacher':users['teacher']})
        if classroom.teacher_id != users['teacher'].pk:
            raise CommandError('Lớp demo đã có giáo viên khác; dừng để bảo toàn dữ liệu.')
        for name in ('demo_student', 'demo_student2'):
            Enrollment.objects.get_or_create(classroom=classroom, student=CustomUser.objects.get(username=name))
        now = timezone.now()
        for skill, title in [('listening','TOEIC Part 1–2'),('speaking','Self Introduction'),('vocabulary','Business English cơ bản')]:
            lesson, _ = Lesson.objects.get_or_create(skill=skill, program='CHUNG', order=900,
                defaults={'title':title,'listening_type':'part12' if skill=='listening' else '', 'created_by':users['admin']})
            if skill == 'listening':
                for order, text, a, b, c, d, correct in [(1,'What is the man doing?','Reading a book','Writing a report','Making a call','Eating lunch','C'),
                                                       (2,'Where are they?','At a station','In an office','At a restaurant','In a park','B')]:
                    ListeningQuestion.objects.get_or_create(lesson=lesson, order=order, defaults=dict(question_text=text,option_a=a,option_b=b,option_c=c,option_d=d,correct_option=correct))
            elif skill=='speaking':
                SpeakingTask.objects.get_or_create(lesson=lesson,order=1,defaults={'sentence':'Introduce your name, hometown and hobbies.'})
            else:
                for word, meaning in [('Resilience','Kiên cường'),('Customer','Khách hàng'),('Deadline','Hạn chót')]:
                    VocabWord.objects.get_or_create(lesson=lesson, word=word, defaults={'meaning':meaning})
            existing=ClassAssignment.objects.filter(lesson=lesson,classroom=classroom).first()
            if existing:
                sync_class_assignment(existing)
            else:
                assign_to_class(actor=users['admin'],lesson=lesson,classroom=classroom,assigned_at=now-timedelta(days=1),due_at=now+timedelta(days=7),repetitions=3)
        self.stdout.write(self.style.SUCCESS('Đã tạo demo_admin, demo_manager, demo_teacher, demo_student, demo_student2 và 3 bài được giao. Không gọi OpenAI; bài nghe mẫu cần bổ sung file nghe thật.'))
