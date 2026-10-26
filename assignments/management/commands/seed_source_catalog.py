"""Retain the original A/B sample catalog without resetting accounts or live content."""
from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from accounts.models import CustomUser
from courses.models import Course, ClassRoom
from assignments.models import Lesson, VocabWord, ListeningQuestion, SpeakingTask


class Command(BaseCommand):
    help = 'Nhập danh mục mẫu của các nhánh A/B; không sửa tài khoản hoặc nội dung đã có.'

    def add_arguments(self, parser):
        parser.add_argument('--owner', help='Tên tài khoản admin/quản lý làm người nhập mẫu')

    @transaction.atomic
    def handle(self, *args, **options):
        if not settings.DEBUG: raise CommandError('Chỉ nhập mẫu trong môi trường DEBUG=True.')
        owner = None
        if options.get('owner'):
            owner = CustomUser.objects.filter(username=options['owner'], role__in=['admin','manager'], is_active=True).first()
            if not owner: raise CommandError('--owner cần là admin/quản lý đang hoạt động.')
        courses = {}
        for code,name,kind in [('TOEIC-INT','Luyen thi TOEIC Cap Toc','TOEIC'),
            ('VSTEP-B2','Chinh phuc VSTEP B2-C1','VSTEP'),('ENG-B1','Tieng Anh B1 Chuan Dau Ra','B1')]:
            courses[code],_ = Course.objects.get_or_create(code=code,defaults={'name':name,'course_type':kind})
        for code,name,course in [('TOEIC-K24','Lop TOEIC 650+ Toi 2-4-6','TOEIC-INT'),
            ('B1-K10','Lop B1 Cap Toc Chieu T7-CN','ENG-B1')]:
            ClassRoom.objects.get_or_create(class_code=code,defaults={'name':name,'course':courses[course],
                'created_by':owner, 'is_active':False})
        samples = [('vocabulary','CHUNG',1,'Business English cơ bản',''),
            ('vocabulary','CHUNG',2,'Business English nâng cao',''),
            ('listening','TOEIC',1,'TOEIC Part 1-2','part12'),
            ('listening','TOEIC',2,'TOEIC Part 3-4','part34'),
            ('speaking','B1',1,'Self Introduction','')]
        for skill,program,order,title,listening_type in samples:
            lesson,created = Lesson.objects.get_or_create(skill=skill,program=program,order=order,
                defaults={'title':title,'listening_type':listening_type,'created_by':owner,'is_active':False,
                    'youtube_url':'https://www.youtube.com/watch?v=jNQXAC9IVRw' if skill=='speaking' else '',
                    'description':'Mẫu từ nhánh assignments. Kiểm tra và bổ sung tài liệu trước khi mở/giao bài.'})
            if not created:
                continue  # Never append example data into an occupied program/lesson slot.
            if skill=='vocabulary' and order==1:
                for n,(word,kind,meaning,example) in enumerate([
                    ('Resilience','Danh từ','Khả năng phục hồi, kiên cường','She showed great resilience.'),
                    ('Customer','Danh từ','Khách hàng','The customer is always right.'),
                    ('Deadline','Danh từ','Hạn chót','Submit before the deadline.')],1):
                    VocabWord.objects.create(lesson=lesson,order=n,word=word,word_type=kind,meaning=meaning,example=example)
            elif skill=='listening' and order==1:
                for n,text,a,b,c,d,correct in [(1,'What is the man doing?','Reading a book','Writing a report','Making a call','Eating lunch','C'),
                    (2,'Where are they?','At a station','In an office','At a restaurant','In a park','B')]:
                    ListeningQuestion.objects.create(lesson=lesson,order=n,question_text=text,option_a=a,option_b=b,option_c=c,option_d=d,correct_option=correct)
            elif skill=='speaking':
                for n,text in enumerate(['Hello, my name is ... and I am from ...','I enjoy reading books and playing sports.'],1):
                    SpeakingTask.objects.create(lesson=lesson,order=n,sentence=text)
        self.stdout.write(self.style.SUCCESS('Đã nhập danh mục nguồn còn thiếu ở dạng nháp. Không đổi mật khẩu, tài khoản, nội dung hoặc lượt giao đã có.'))
