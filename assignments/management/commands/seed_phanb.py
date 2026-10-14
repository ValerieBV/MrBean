from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand

from assignments.models import Lesson, VocabWord, ListeningQuestion, SpeakingTask, Skill, Program, ListeningType

User = get_user_model()


class Command(BaseCommand):
    help = "Tạo dữ liệu mẫu Phần B"

    def handle(self, *args, **opts):
        admin, c = User.objects.get_or_create(
            username="admin", defaults={"role": "admin", "is_staff": True, "is_superuser": True}
        )
        if c:
            admin.set_password("123"); admin.save()
        hv, c = User.objects.get_or_create(
            username="hocvien", defaults={"role": "student", "first_name": "Lê Văn", "last_name": "An"}
        )
        if c:
            hv.set_password("123"); hv.save()

        v1, _ = Lesson.objects.get_or_create(
            skill=Skill.VOCABULARY, program=Program.CHUNG, order=1,
            defaults={"title": "Business English cơ bản", "created_by": admin},
        )
        for i, (w, t, m, ex) in enumerate([
            ("Resilience", "Danh từ", "Khả năng phục hồi, kiên cường", "She showed great resilience."),
            ("Customer", "Danh từ", "Khách hàng", "The customer is always right."),
            ("Deadline", "Danh từ", "Hạn chót", "Submit before the deadline."),
        ], 1):
            VocabWord.objects.get_or_create(lesson=v1, order=i, word=w, defaults={"word_type": t, "meaning": m, "example": ex})
        Lesson.objects.get_or_create(skill=Skill.VOCABULARY, program=Program.CHUNG, order=2,
                                     defaults={"title": "Business English nâng cao", "created_by": admin})

        l1, _ = Lesson.objects.get_or_create(
            skill=Skill.LISTENING, program=Program.TOEIC, order=1,
            defaults={"title": "TOEIC Part 1-2", "listening_type": ListeningType.PART12, "created_by": admin},
        )
        ListeningQuestion.objects.get_or_create(
            lesson=l1, order=1, defaults={
                "question_text": "What is the man doing?",
                "option_a": "Reading a book", "option_b": "Writing a report",
                "option_c": "Making a call", "option_d": "Eating lunch", "correct_option": "C"},
        )
        ListeningQuestion.objects.get_or_create(
            lesson=l1, order=2, defaults={
                "question_text": "Where are they?",
                "option_a": "At a station", "option_b": "In an office",
                "option_c": "At a restaurant", "option_d": "In a park", "correct_option": "B"},
        )
        Lesson.objects.get_or_create(skill=Skill.LISTENING, program=Program.TOEIC, order=2,
                                     defaults={"title": "TOEIC Part 3-4", "listening_type": ListeningType.PART34, "created_by": admin})

        s1, _ = Lesson.objects.get_or_create(
            skill=Skill.SPEAKING, program=Program.B1, order=1,
            defaults={"title": "Self Introduction", "youtube_url": "https://www.youtube.com/watch?v=jNQXAC9IVRw", "created_by": admin},
        )
        SpeakingTask.objects.get_or_create(lesson=s1, order=1, defaults={"sentence": "Hello, my name is ... and I am from ..."})
        SpeakingTask.objects.get_or_create(lesson=s1, order=2, defaults={"sentence": "I enjoy reading books and playing sports."})

        self.stdout.write(self.style.SUCCESS("Xong! Tài khoản: admin/123 (quản trị), hocvien/123 (học viên)."))
