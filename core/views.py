from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect


@login_required
def home(request):
    from accounts.views import home_for
    return redirect(home_for(request.user))
