def student_info(request):
    user=getattr(request,'user',None)
    if not user or not user.is_authenticated:
        return {}
    enrollment=user.class_enrollments.filter(status='active').select_related('classroom__course').first()
    return {'student_info':{'ho_ten':user.get_full_name() or user.username,'ma_hv':user.student_code or user.username},
            'current_class':enrollment.classroom if enrollment else None}
