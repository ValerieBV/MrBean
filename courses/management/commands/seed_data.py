from django.core.management.base import BaseCommand
from accounts.models import CustomUser
from courses.models import Course, ClassRoom, Enrollment
from courses.services import ClassManagementService


class Command(BaseCommand):
    help = 'Khoi tao du lieu mau cho he thong Mr Bean (Admin, Quan ly, Giao vien, Hoc vien, Lop hoc)'

    def handle(self, *args, **kwargs):
        self.stdout.write("Khoi tao du lieu mau...")

        # 1. Tao Tai khoan
        admin, _ = CustomUser.objects.get_or_create(
            username='admin',
            defaults={
                'first_name': 'Admin',
                'last_name': 'He Thong',
                'email': 'admin@mrbean.edu.vn',
                'role': CustomUser.ROLE_ADMIN,
                'is_staff': True,
                'is_superuser': True
            }
        )
        admin.set_password('admin123')
        admin.save()

        manager, _ = CustomUser.objects.get_or_create(
            username='quanly1',
            defaults={
                'first_name': 'Nguyen',
                'last_name': 'Quan Ly',
                'email': 'quanly@mrbean.edu.vn',
                'role': CustomUser.ROLE_MANAGER,
                'is_staff': True
            }
        )
        manager.set_password('quanly123')
        manager.save()

        teacher, _ = CustomUser.objects.get_or_create(
            username='gv_bean',
            defaults={
                'first_name': 'Mr',
                'last_name': 'Bean',
                'email': 'teacher@mrbean.edu.vn',
                'role': CustomUser.ROLE_TEACHER
            }
        )
        teacher.set_password('teacher123')
        teacher.save()

        student1, _ = CustomUser.objects.get_or_create(
            username='hocvien1',
            defaults={
                'first_name': 'Tran',
                'last_name': 'Hoc Vien 1',
                'email': 'student1@mrbean.edu.vn',
                'role': CustomUser.ROLE_STUDENT
            }
        )
        student1.set_password('student123')
        student1.save()

        student2, _ = CustomUser.objects.get_or_create(
            username='hocvien2',
            defaults={
                'first_name': 'Le',
                'last_name': 'Hoc Vien 2',
                'email': 'student2@mrbean.edu.vn',
                'role': CustomUser.ROLE_STUDENT
            }
        )
        student2.set_password('student123')
        student2.save()

        # 2. Tao Khoa hoc
        course_toeic, _ = Course.objects.get_or_create(
            code='TOEIC-INT',
            defaults={
                'name': 'Luyen thi TOEIC Cap Toc',
                'course_type': Course.COURSE_TYPE_TOEIC
            }
        )

        course_vstep, _ = Course.objects.get_or_create(
            code='VSTEP-B2',
            defaults={
                'name': 'Chinh phuc VSTEP B2-C1',
                'course_type': Course.COURSE_TYPE_VSTEP
            }
        )

        course_b1, _ = Course.objects.get_or_create(
            code='ENG-B1',
            defaults={
                'name': 'Tieng Anh B1 Chuan Dau Ra',
                'course_type': Course.COURSE_TYPE_B1
            }
        )

        # 3. Tao Lop hoc & Phan cong giao vien
        class_toeic, _ = ClassRoom.objects.get_or_create(
            class_code='TOEIC-K24',
            defaults={
                'name': 'Lop TOEIC 650+ Toi 2-4-6',
                'course': course_toeic,
                'teacher': teacher,
                'created_by': manager
            }
        )

        class_b1, _ = ClassRoom.objects.get_or_create(
            class_code='B1-K10',
            defaults={
                'name': 'Lop B1 Cap Toc Chieu T7-CN',
                'course': course_b1,
                'teacher': teacher,
                'created_by': manager
            }
        )

        # 4. Them hoc vien vao lop
        if not Enrollment.objects.filter(classroom=class_toeic, student=student1).exists():
            ClassManagementService.enroll_student_to_class(class_toeic, student1)

        if not Enrollment.objects.filter(classroom=class_b1, student=student2).exists():
            ClassManagementService.enroll_student_to_class(class_b1, student2)

        self.stdout.write(self.style.SUCCESS("Da khoi tao du lieu mau thanh cong!"))
        self.stdout.write("""
Accounts:
1. Admin:    admin / admin123        (Toan quyen quan tri)
2. Quan ly:  quanly1 / quanly123     (Giao bai tap, nhan thong bao mien BTVN)
3. Giao vien: gv_bean / teacher123    (Cham bai lop TOEIC-K24, B1-K10; duyet mien BTVN nghe)
4. Hoc vien 1: hocvien1 / student123 (Lop TOEIC: Duoc cap 08 buoi mien nghe)
5. Hoc vien 2: hocvien2 / student123 (Lop B1: Duoc cap 05 buoi mien nghe)
""")
