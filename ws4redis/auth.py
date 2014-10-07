# -*- coding: utf-8 -*-
from django.conf import settings
from django.utils.importlib import import_module
from django.utils.functional import SimpleLazyObject


def get_user_from_session(request):
    if 'django.contrib.sessions.middleware.SessionMiddleware' in settings.MIDDLEWARE_CLASSES:
        engine = import_module(settings.SESSION_ENGINE)
        session_key = request.COOKIES.get(settings.SESSION_COOKIE_NAME, None)
        if session_key:
            request.session = engine.SessionStore(session_key)
            if 'django.contrib.auth.middleware.AuthenticationMiddleware' in settings.MIDDLEWARE_CLASSES:
                from django.contrib.auth import get_user
                request.user = SimpleLazyObject(lambda: get_user(request))
    return request.user
