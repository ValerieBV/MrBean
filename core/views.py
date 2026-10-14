from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect


@login_required
def home(request):
    role = getattr(request.user, "role", None)
    if role == "student" and not request.user.is_staff:
        return redirect("submissions:dashboard")
    return redirect("assignment_list")
