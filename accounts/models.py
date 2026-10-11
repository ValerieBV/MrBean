from django.contrib.auth.models import AbstractUser
from django.db import models

class CustomUser(AbstractUser):
    # Định nghĩa 4 vai trò theo yêu cầu BRD
    ROLE_CHOICES = (
        ('admin', 'Admin'),
        ('manager', 'Quản lý'),
        ('teacher', 'Giáo viên/CTV'),
        ('student', 'Học viên'),
    )

    role = models.CharField(max_length=20, choices=ROLE_CHOICES, default='student')
    phone_number = models.CharField(max_length=15, blank=True, null=True)

    # Thêm related_name để tránh xung đột với auth.User mặc định của Django
    groups = models.ManyToManyField(
        'auth.Group',
        verbose_name='groups',
        blank=True,
        help_text='The groups this user belongs to. A user will get all permissions granted to each of their groups.',
        related_name="customuser_set",
        related_query_name="user",
    )
    user_permissions = models.ManyToManyField(
        'auth.Permission',
        verbose_name='user permissions',
        blank=True,
        help_text='Specific permissions for this user.',
        related_name="customuser_set",
        related_query_name="user",
    )

    def __str__(self):
        return f"{self.username} - {self.get_role_display()}"
