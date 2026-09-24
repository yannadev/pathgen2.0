"""Fail-closed Railway production settings."""

import os

from config.environment import postgres_database, validate_production_environment

from .base import *  # noqa: F401,F403


PRODUCTION_ENVIRONMENT = validate_production_environment(os.environ)

MIDDLEWARE.insert(1, "whitenoise.middleware.WhiteNoiseMiddleware")  # noqa: F405

SECRET_KEY = PRODUCTION_ENVIRONMENT.secret_key
DEBUG = False
ALLOWED_HOSTS = PRODUCTION_ENVIRONMENT.allowed_hosts
CSRF_TRUSTED_ORIGINS = PRODUCTION_ENVIRONMENT.csrf_trusted_origins
DATABASES = {
    "default": postgres_database(
        PRODUCTION_ENVIRONMENT.database_url,
        conn_max_age=60,
    )
}
GROQ_API_KEY = PRODUCTION_ENVIRONMENT.groq_api_key
GROQ_MODEL = PRODUCTION_ENVIRONMENT.groq_model
OPENAI_API_KEY = PRODUCTION_ENVIRONMENT.openai_api_key
EMBEDDING_MODEL = PRODUCTION_ENVIRONMENT.embedding_model

SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
SECURE_SSL_REDIRECT = True
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True
SECURE_HSTS_SECONDS = 31_536_000
SECURE_HSTS_INCLUDE_SUBDOMAINS = True
SECURE_HSTS_PRELOAD = True
SECURE_CONTENT_TYPE_NOSNIFF = True
X_FRAME_OPTIONS = "DENY"

STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {
        "BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage"
    },
}
