"""Deterministic settings for tests and CI checks."""

import os


os.environ.setdefault("SECRET_KEY", "test-only-pathgen-secret-key")
os.environ.setdefault(
    "DATABASE_URL",
    "postgresql://pathgen_test:pathgen_test@localhost:5432/pathgen_test",
)
os.environ.setdefault("GROQ_MODEL", "gpt-oss-120b")
os.environ.setdefault("EMBEDDING_MODEL", "text-embedding-3-small")

from .base import *  # noqa: E402,F403


DEBUG = False
PASSWORD_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]
EMAIL_BACKEND = "django.core.mail.backends.locmem.EmailBackend"
