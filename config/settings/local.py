"""Local development settings."""

from pathlib import Path

from dotenv import load_dotenv


load_dotenv(Path(__file__).resolve().parents[2] / ".env", override=False)

from .base import *  # noqa: E402,F403


DEBUG = env_bool("DEBUG", default=True)  # noqa: F405
ALLOWED_HOSTS = env_list("ALLOWED_HOSTS") or ["localhost", "127.0.0.1", "[::1]"]  # noqa: F405
