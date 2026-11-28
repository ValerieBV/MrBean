from datetime import timedelta
import io
from PIL import Image
import tempfile
from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.utils import timezone
from courses.models import Course, ClassRoom, Enrollment
from assignments.models import Lesson, VocabWord, ListeningQuestion, SpeakingTask
from assignments.services import assign_to_class


@override_settings(AI_LOCAL_ENABLED=False)
class IntegratedFixture(TestCase):
    def setUp(self):
        media = tempfile.TemporaryDirectory()
        self.addCleanup(media.cleanup)
        media_settings = override_settings(MEDIA_ROOT=media.name)
        media_settings.enable()
        self.addCleanup(media_settings.disable)
        self.now = timezone.now()
        User = get_user_model()
        self.admin = User.objects.create_user(username='boss', role='admin')
        self.manager = User.objects.create_user(username='manager', role='manager')
        self.teacher = User.objects.create_user(username='teacher', role='teacher')
        self.other_teacher = User.objects.create_user(username='other_teacher', role='teacher')
        self.student = User.objects.create_user(username='student', role='student')
        self.other_student = User.objects.create_user(username='other_student', role='student')
        course = Course.objects.create(code='TOEIC', name='TOEIC')
        self.classroom = ClassRoom.objects.create(class_code='C1', name='Class 1', course=course, teacher=self.teacher)
        self.other_classroom = ClassRoom.objects.create(class_code='C2', name='Class 2', course=course, teacher=self.other_teacher)
        Enrollment.objects.create(classroom=self.classroom, student=self.student)
        Enrollment.objects.create(classroom=self.other_classroom, student=self.other_student)
        self.speaking = Lesson.objects.create(skill='speaking', program='CHUNG', order=1, title='Read the video script',
            youtube_url='https://www.youtube.com/watch?v=abcdefghijk', reference_transcript='My hobby is reading.', created_by=self.teacher)
        SpeakingTask.objects.create(lesson=self.speaking, sentence='My hobby is reading.')
        self.vocab = Lesson.objects.create(skill='vocabulary', program='CHUNG', order=1, title='Business vocabulary', created_by=self.teacher)
        VocabWord.objects.create(lesson=self.vocab, word='Customer', meaning='Khách hàng')
        VocabWord.objects.create(lesson=self.vocab, word='Deadline', meaning='Hạn chót')
        self.listening = Lesson.objects.create(skill='listening', program='CHUNG', order=1, title='Listening quiz', listening_type='part12', created_by=self.teacher)
        self.q1 = ListeningQuestion.objects.create(lesson=self.listening, question_text='Question1',option_a='a1',option_b='b1',correct_option='B')
        self.q2 = ListeningQuestion.objects.create(lesson=self.listening, question_text='Question2',option_a='a2',option_b='b2',correct_option='A')
        self.assignments = {}
        for lesson in [self.speaking, self.vocab, self.listening]:
            self.assignments[lesson.skill] = assign_to_class(actor=self.teacher, lesson=lesson, classroom=self.classroom,
                assigned_at=self.now-timedelta(days=1), due_at=self.now+timedelta(days=1), repetitions=3)
        self.task = self.assignments['speaking'].tasks.get(learner=self.student)
        self.vocab_task = self.assignments['vocabulary'].tasks.get(learner=self.student)
        self.listening_task = self.assignments['listening'].tasks.get(learner=self.student)

    @staticmethod
    def audio():
        return SimpleUploadedFile('speech.webm', b'fake-test-audio', content_type='audio/webm')

    @staticmethod
    def vocabulary_image():
        stream = io.BytesIO()
        Image.new('RGB', (20, 20), 'white').save(stream, 'PNG')
        return SimpleUploadedFile('page.png', stream.getvalue(), content_type='image/png')
