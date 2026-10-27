def current_enrollment(request):
    user=getattr(request,'user',None)
    if not user or not user.is_authenticated or user.role!='student':return None
    rows=user.class_enrollments.filter(status='active').select_related('classroom__course')
    selected=request.session.get('learning_class_id')
    return (rows.filter(classroom_id=selected).first() if isinstance(selected,int) else None) or rows.first()


def student_info(request):
    user=getattr(request,'user',None)
    if not user or not user.is_authenticated:
        return {}
    enrollment=current_enrollment(request)
    classroom=enrollment.classroom if enrollment else None
    return {'student_info':{'ho_ten':user.get_full_name() or user.username,'ma_hv':user.student_code or user.username,
            'chung_chi':classroom.course.get_course_type_display() if classroom else '',
            'khoa':classroom.name if classroom else '', 'co_so':''},
            'current_class':{'cert':classroom.course.get_course_type_display(),'name':classroom.name,
                             'code':classroom.class_code} if classroom else None}
