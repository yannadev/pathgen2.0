"""Local development settings."""

from pathlib import Path

from dotenv import load_dotenv


load_dotenv(Path(__file__).resolve().parents[2] / ".env", override=False)

from .base import *  # noqa: E402,F403


# Local runserver must serve discovered development assets even when a shared
# environment file keeps the production-safe DEBUG default disabled.
DEBUG = True
ALLOWED_HOSTS = env_list("ALLOWED_HOSTS") or ["localhost", "127.0.0.1", "[::1]"]  # noqa: F405
