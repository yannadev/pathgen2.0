from __future__ import annotations

from django.contrib.sessions.models import Session
from django.utils import timezone

from apps.accounts.models import User


def invalidate_user_sessions(
    user: User,
    *,
    exclude_session_key: str | None = None,
) -> int:
    """Delete every live authenticated session for a user except an optional current one."""
    session_keys: list[str] = []
    sessions = Session.objects.filter(expire_date__gte=timezone.now())
    if exclude_session_key:
        sessions = sessions.exclude(session_key=exclude_session_key)
    for session in sessions.iterator():
        try:
            authenticated_user_id = session.get_decoded().get("_auth_user_id")
        except Exception:  # Corrupt/expired session data is not an account match.
            continue
        if authenticated_user_id == str(user.pk):
            session_keys.append(session.session_key)
    if session_keys:
        Session.objects.filter(session_key__in=session_keys).delete()
    return len(session_keys)

