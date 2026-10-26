from functools import wraps

from django.db import connections, router
from django.shortcuts import render

from .models import Conversation, Message, TutorAttempt
from .permissions import is_admin


def support_schema_ready():
    """Check the additive support tables without writing during a request.

    Do not cache this: the next request must work after the operator migrates.
    Other database errors remain visible to monitoring rather than being hidden.
    """
    connection = connections[router.db_for_read(Conversation)]
    required = {model._meta.db_table for model in (Conversation, Message, TutorAttempt)}
    return required.issubset(connection.introspection.table_names())


def require_support_tables(view):
    @wraps(view)
    def wrapped(request, *args, **kwargs):
        if not support_schema_ready():
            response = render(request, 'support/unavailable.html', {
                'support_is_contact': True,
                'can_configure_support': is_admin(request.user),
            }, status=503)
            response['Cache-Control'] = 'private, no-store'
            response['Retry-After'] = '60'
            return response
        return view(request, *args, **kwargs)
    return wrapped
