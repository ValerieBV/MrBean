from django.contrib import admin
from django.utils.html import format_html
from django.contrib import messages
from courses.models import Course, ClassRoom, Enrollment, StudentExemptionQuota, ExemptionRequest


class EnrollmentInline(admin.TabularInline):
    model = Enrollment
    extra = 1
    fields = ('student', 'status', 'enrolled_at')
    readonly_fields = ('enrolled_at',)
    autocomplete_fields = ('student',)


@admin.register(Course)
class CourseAdmin(admin.ModelAdmin):
    list_display = (
        'code',
        'name',
        'course_type',
        'default_listening_exemption_quota',
        'created_at'
    )
    list_filter = ('course_type',)
    search_fields = ('code', 'name')
    readonly_fields = ('created_at', 'updated_at')


@admin.register(ClassRoom)
class ClassRoomAdmin(admin.ModelAdmin):
    list_display = (
        'class_code',
        'name',
        'course',
        'teacher_display',
        'total_students_display',
        'is_active',
        'start_date'
    )
    list_filter = ('course', 'is_active', 'teacher')
    search_fields = ('class_code', 'name')
    inlines = [EnrollmentInline]

    def teacher_display(self, obj):
        if obj.teacher:
            name = obj.teacher.get_full_name() or obj.teacher.username
            return format_html('<strong>{}</strong>', name)
        return format_html('<span style="color: red;">Chưa phân công</span>')
    teacher_display.short_description = "Giáo viên phụ trách"

    def total_students_display(self, obj):
        count = obj.total_students
        return format_html('<span>{} học viên</span>', count)
    total_students_display.short_description = "Sĩ số lớp"


@admin.register(Enrollment)
class EnrollmentAdmin(admin.ModelAdmin):
    list_display = ('student', 'classroom', 'status', 'enrolled_at', 'quota_display')
    list_filter = ('status', 'classroom')
    search_fields = ('student__username', 'student__first_name', 'student__last_name', 'classroom__class_code')
    autocomplete_fields = ('student', 'classroom')

    def quota_display(self, obj):
        quota = getattr(obj, 'exemption_quota', None)
        if quota:
            return f"Còn {quota.remaining_quota}/{quota.max_quota} buổi"
        return "Chưa kích hoạt"
    quota_display.short_description = "Hạn mức miễn nghe"


@admin.register(StudentExemptionQuota)
class StudentExemptionQuotaAdmin(admin.ModelAdmin):
    list_display = (
        'student_username',
        'class_info',
        'course_type_badge',
        'used_quota',
        'max_quota',
        'remaining_badge'
    )
    list_filter = ('enrollment__classroom__course__course_type',)
    search_fields = ('enrollment__student__username', 'enrollment__classroom__class_code')

    def student_username(self, obj):
        return obj.enrollment.student.username
    student_username.short_description = "Học viên"

    def class_info(self, obj):
        return f"{obj.enrollment.classroom.class_code} - {obj.enrollment.classroom.name}"
    class_info.short_description = "Lớp học"

    def course_type_badge(self, obj):
        return obj.enrollment.classroom.course.get_course_type_display()
    course_type_badge.short_description = "Chương trình"

    def remaining_badge(self, obj):
        rem = obj.remaining_quota
        color = "green" if rem > 2 else ("orange" if rem > 0 else "red")
        return format_html('<span style="color: {}; font-weight: bold;">{} / {} buổi</span>', color, rem, obj.max_quota)
    remaining_badge.short_description = "Buổi còn lại"


@admin.register(ExemptionRequest)
class ExemptionRequestAdmin(admin.ModelAdmin):
    list_display = (
        'id',
        'student_display',
        'class_display',
        'session_title',
        'homework_type_badge',
        'status_badge',
        'quota_remaining_display',
        'reviewed_by',
        'created_at'
    )
    list_filter = ('status', 'homework_type', 'enrollment__classroom')
    search_fields = ('enrollment__student__username', 'session_title', 'reason')
    actions = ['approve_requests_action', 'reject_requests_action']

    def student_display(self, obj):
        return obj.enrollment.student.get_full_name() or obj.enrollment.student.username
    student_display.short_description = "Học viên"

    def class_display(self, obj):
        return obj.enrollment.classroom.class_code
    class_display.short_description = "Lớp"

    def homework_type_badge(self, obj):
        if obj.homework_type == ExemptionRequest.HOMEWORK_TYPE_LISTENING:
            return format_html('<span style="color: green; font-weight: bold;">Listening (Hợp lệ)</span>')
        return format_html('<span style="color: red; font-weight: bold;">{} (Không hợp lệ)</span>', obj.get_homework_type_display())
    homework_type_badge.short_description = "Loại BTVN"

    def status_badge(self, obj):
        if obj.status == ExemptionRequest.STATUS_APPROVED:
            return format_html('<span style="color: green; font-weight: bold;">✔ Đã duyệt</span>')
        elif obj.status == ExemptionRequest.STATUS_REJECTED:
            return format_html('<span style="color: red; font-weight: bold;">✖ Từ chối</span>')
        return format_html('<span style="color: orange; font-weight: bold;">⏳ Chờ duyệt</span>')
    status_badge.short_description = "Trạng thái"

    def quota_remaining_display(self, obj):
        quota = getattr(obj.enrollment, 'exemption_quota', None)
        if quota:
            return f"Còn {quota.remaining_quota}/{quota.max_quota} buổi"
        return "-"
    quota_remaining_display.short_description = "Quota còn lại"

    @admin.action(description="✔ Duyệt các đơn xin miễn BTVN nghe đã chọn")
    def approve_requests_action(self, request, queryset):
        count = 0
        for req in queryset:
            if req.status == ExemptionRequest.STATUS_PENDING:
                try:
                    req.approve(teacher_user=request.user, note="Admin duyệt hàng loạt")
                    count += 1
                except Exception as e:
                    self.message_user(request, f"Lỗi khi duyệt đơn #{req.id}: {str(e)}", level=messages.ERROR)
        self.message_user(request, f"Đã duyệt thành công {count} đơn xin miễn BTVN.", level=messages.SUCCESS)

    @admin.action(description="✖ Từ chối các đơn xin miễn BTVN đã chọn")
    def reject_requests_action(self, request, queryset):
        count = 0
        for req in queryset:
            if req.status == ExemptionRequest.STATUS_PENDING:
                try:
                    req.reject(teacher_user=request.user, reason="Admin từ chối hàng loạt")
                    count += 1
                except Exception as e:
                    self.message_user(request, f"Lỗi từ chối đơn #{req.id}: {str(e)}", level=messages.ERROR)
        self.message_user(request, f"Đã từ chối {count} đơn xin miễn BTVN.", level=messages.WARNING)
