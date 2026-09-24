"""Small, testable helpers for PathGen's environment contract."""

from __future__ import annotations

import os
from collections.abc import Mapping
from dataclasses import dataclass
from urllib.parse import urlsplit

import dj_database_url
from django.core.exceptions import ImproperlyConfigured


APPROVED_GROQ_MODEL = "gpt-oss-120b"
APPROVED_EMBEDDING_MODEL = "text-embedding-3-small"
POSTGRES_SCHEMES = frozenset({"postgres", "postgresql"})


def env_bool(name: str, *, default: bool, environ: Mapping[str, str] | None = None) -> bool:
    source = os.environ if environ is None else environ
    raw_value = source.get(name)
    if raw_value is None or not raw_value.strip():
        return default
    normalized = raw_value.strip().lower()
    if normalized in {"1", "true", "yes", "on"}:
        return True
    if normalized in {"0", "false", "no", "off"}:
        return False
    raise ImproperlyConfigured(f"{name} must be a boolean value.")


def env_list(name: str, *, environ: Mapping[str, str] | None = None) -> list[str]:
    source = os.environ if environ is None else environ
    return [item.strip() for item in source.get(name, "").split(",") if item.strip()]


def require_env(name: str, *, environ: Mapping[str, str] | None = None) -> str:
    source = os.environ if environ is None else environ
    value = source.get(name, "").strip()
    if not value:
        raise ImproperlyConfigured(f"{name} must be set and nonblank.")
    return value


def validate_model_identifiers(
    *,
    groq_model: str,
    embedding_model: str,
) -> None:
    if groq_model != APPROVED_GROQ_MODEL:
        raise ImproperlyConfigured(
            f"GROQ_MODEL must be exactly {APPROVED_GROQ_MODEL}."
        )
    if embedding_model != APPROVED_EMBEDDING_MODEL:
        raise ImproperlyConfigured(
            f"EMBEDDING_MODEL must be exactly {APPROVED_EMBEDDING_MODEL}."
        )


def postgres_database(url: str, *, conn_max_age: int = 0) -> dict[str, object]:
    scheme = urlsplit(url).scheme.lower()
    if scheme not in POSTGRES_SCHEMES:
        raise ImproperlyConfigured(
            "DATABASE_URL must use the postgres:// or postgresql:// scheme."
        )
    return dj_database_url.parse(
        url,
        conn_max_age=conn_max_age,
        conn_health_checks=conn_max_age > 0,
    )


@dataclass(frozen=True)
class ProductionEnvironment:
    secret_key: str
    allowed_hosts: list[str]
    csrf_trusted_origins: list[str]
    database_url: str
    groq_api_key: str
    groq_model: str
    openai_api_key: str
    embedding_model: str


def validate_production_environment(
    environ: Mapping[str, str] | None = None,
) -> ProductionEnvironment:
    source = os.environ if environ is None else environ
    if env_bool("DEBUG", default=False, environ=source):
        raise ImproperlyConfigured("DEBUG must be False in production.")

    allowed_hosts = env_list("ALLOWED_HOSTS", environ=source)
    if not allowed_hosts or "*" in allowed_hosts:
        raise ImproperlyConfigured(
            "ALLOWED_HOSTS must contain explicit production hosts and cannot use '*'."
        )

    trusted_origins = env_list("CSRF_TRUSTED_ORIGINS", environ=source)
    if not trusted_origins or any(
        not origin.startswith("https://") for origin in trusted_origins
    ):
        raise ImproperlyConfigured(
            "CSRF_TRUSTED_ORIGINS must contain explicit HTTPS origins."
        )

    database_url = require_env("DATABASE_URL", environ=source)
    postgres_database(database_url, conn_max_age=60)

    groq_model = require_env("GROQ_MODEL", environ=source)
    embedding_model = require_env("EMBEDDING_MODEL", environ=source)
    validate_model_identifiers(
        groq_model=groq_model,
        embedding_model=embedding_model,
    )

    return ProductionEnvironment(
        secret_key=require_env("SECRET_KEY", environ=source),
        allowed_hosts=allowed_hosts,
        csrf_trusted_origins=trusted_origins,
        database_url=database_url,
        groq_api_key=require_env("GROQ_API_KEY", environ=source),
        groq_model=groq_model,
        openai_api_key=require_env("OPENAI_API_KEY", environ=source),
        embedding_model=embedding_model,
    )
