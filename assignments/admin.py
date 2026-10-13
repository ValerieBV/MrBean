# Register your models here.
from django.contrib import admin
from .models import assignment
@admin.register(assignment)
class AssignmentAdmin(admin.ModelAdmin):

    # Các cột hiển thị trong danh sách bài tập
    list_display = (
        "code",
        "title",
        "category",
        "program",
        "is_active",
        "created_at",
    )

    # Bộ lọc bên phải
    list_filter = (
        "category",
        "program",
        "is_active",
        "created_at",
    )

    # Tìm kiếm theo mã và tên bài tập
    search_fields = (
        "code",
        "title",
        "description",
    )

    # Sắp xếp theo ngày tạo mới nhất
    ordering = ("-created_at",)

    # Chia các trường thành từng nhóm khi thêm hoặc sửa
    fieldsets = (
        ("Thông tin bài tập", {
            "fields": (
                "code",
                "title",
                "category",
                "program",
                "description",
            )
        }),
        ("Nội dung bài tập", {
            "fields": (
                "content",
                "audio_file",
                "attachment",
                "answer_key",
            )
        }),
        ("Thông tin quản lý", {
            "fields": (
                "created_by",
                "is_active",
            )
        }),
    )

    # Hiển thị các trường này nhưng không cho chỉnh sửa
    readonly_fields = (
        "created_at",
        "updated_at",
    )

    # Phân trang
    list_per_page = 20
