"""Settings shared by every PathGen environment."""

from __future__ import annotations

import os
from pathlib import Path

from config.environment import (
    APPROVED_EMBEDDING_MODEL,
    APPROVED_GROQ_MODEL,
    env_bool,
    env_list,
    postgres_database,
    validate_model_identifiers,
)


BASE_DIR = Path(__file__).resolve().parents[2]

SECRET_KEY = os.environ.get("SECRET_KEY", "") or "unsafe-local-pathgen-key"
DEBUG = env_bool("DEBUG", default=False)
ALLOWED_HOSTS = env_list("ALLOWED_HOSTS")

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "apps.accounts",
    "apps.classrooms",
    "apps.curriculum",
    "apps.learning",
    "apps.adaptive",
    "apps.feedback",
    "apps.core",
]

AUTH_USER_MODEL = "accounts.User"

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "apps.accounts.middleware.AuthenticatedSessionLifetimeMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "config.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

WSGI_APPLICATION = "config.wsgi.application"
ASGI_APPLICATION = "config.asgi.application"

DATABASE_URL = os.environ.get(
    "DATABASE_URL",
    "postgresql://pathgen:pathgen@localhost:5432/pathgen",
)
DATABASES = {"default": postgres_database(DATABASE_URL)}

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

LOGIN_URL = "account:login"
LOGIN_REDIRECT_URL = "account:my_account"
LOGOUT_REDIRECT_URL = "account:login"

SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = "Lax"
SESSION_COOKIE_AGE = 8 * 60 * 60
SESSION_EXPIRE_AT_BROWSER_CLOSE = True
PATHGEN_SESSION_ABSOLUTE_AGE = 8 * 60 * 60
PATHGEN_SESSION_IDLE_AGE = 30 * 60

LANGUAGE_CODE = "en-us"
TIME_ZONE = "Asia/Manila"
USE_I18N = True
USE_TZ = True

STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
STATIC_DIST_DIR = BASE_DIR / "static" / "dist"
STATIC_FONT_DIR = BASE_DIR / "static" / "src" / "fonts"
STATIC_IMAGE_DIR = BASE_DIR / "static" / "src" / "images"
STATICFILES_DIRS = []
if STATIC_DIST_DIR.exists():
    STATICFILES_DIRS.append(("dist", STATIC_DIST_DIR))
if STATIC_FONT_DIR.exists():
    STATICFILES_DIRS.append(("fonts", STATIC_FONT_DIR))
if STATIC_IMAGE_DIR.exists():
    STATICFILES_DIRS.append(("images", STATIC_IMAGE_DIR))

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

GROQ_API_KEY = os.environ.get("GROQ_API_KEY", "")
GROQ_MODEL = os.environ.get("GROQ_MODEL", APPROVED_GROQ_MODEL)
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY", "")
EMBEDDING_MODEL = os.environ.get(
    "EMBEDDING_MODEL",
    APPROVED_EMBEDDING_MODEL,
)
validate_model_identifiers(
    groq_model=GROQ_MODEL,
    embedding_model=EMBEDDING_MODEL,
)

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "standard": {
            "format": "{asctime} {levelname} {name} {message}",
            "style": "{",
        },
    },
    "handlers": {
        "console": {
            "class": "logging.StreamHandler",
            "formatter": "standard",
        },
    },
    "root": {"handlers": ["console"], "level": "INFO"},
    "loggers": {
        "django": {
            "handlers": ["console"],
            "level": os.environ.get("DJANGO_LOG_LEVEL", "INFO"),
            "propagate": False,
        },
    },
}
