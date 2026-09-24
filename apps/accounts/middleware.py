from __future__ import annotations

import time
from urllib.parse import urlencode

from django.conf import settings
from django.contrib.auth import logout
from django.http import HttpRequest, HttpResponse, HttpResponseRedirect
from django.urls import reverse


SESSION_STARTED_KEY = "_pathgen_session_started_at"
SESSION_SEEN_KEY = "_pathgen_session_seen_at"


def initialize_session_lifetime(request: HttpRequest) -> None:
    now = int(time.time())
    request.session[SESSION_STARTED_KEY] = now
    request.session[SESSION_SEEN_KEY] = now


class AuthenticatedSessionLifetimeMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request: HttpRequest) -> HttpResponse:
        if request.user.is_authenticated:
            now = int(time.time())
            started_at = request.session.get(SESSION_STARTED_KEY, now)
            seen_at = request.session.get(SESSION_SEEN_KEY, now)
            absolute_expired = now - started_at > settings.PATHGEN_SESSION_ABSOLUTE_AGE
            idle_expired = now - seen_at > settings.PATHGEN_SESSION_IDLE_AGE
            if absolute_expired or idle_expired:
                logout(request)
                login_url = reverse("account:login")
                if request.method == "GET":
                    login_url = f"{login_url}?{urlencode({'next': request.path})}"
                return HttpResponseRedirect(login_url)
            request.session.setdefault(SESSION_STARTED_KEY, started_at)
            request.session[SESSION_SEEN_KEY] = now
        return self.get_response(request)

