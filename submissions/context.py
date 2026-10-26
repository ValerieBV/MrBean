def student_info(request):
    u = getattr(request, "user", None)
    if not u or not u.is_authenticated:
        return {}
    return {
        "student_info": {
            "ho_ten": u.get_full_name() or u.username,
            "ma_hv": u.username,
            "chung_chi": "TOEIC",
            "khoa": "Khóa 2025-2026",
            "co_so": "Cơ sở 1",
        },
        "current_class": getattr(request, "session", {}).get("current_class"),
    }
