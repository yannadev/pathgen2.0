"""Deterministic settings for tests and CI checks."""

import os
from pathlib import Path

from dotenv import load_dotenv

from config.environment import postgres_database, require_env


load_dotenv(Path(__file__).resolve().parents[2] / ".env", override=False)

_database_url = require_env("DATABASE_URL")
postgres_database(_database_url)

os.environ.setdefault("SECRET_KEY", "test-only-pathgen-secret-key")
os.environ.setdefault("GROQ_MODEL", "gpt-oss-120b")
os.environ.setdefault("EMBEDDING_MODEL", "text-embedding-3-small")

from .base import *  # noqa: E402,F403


DEBUG = False
PASSWORD_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]
EMAIL_BACKEND = "django.core.mail.backends.locmem.EmailBackend"
