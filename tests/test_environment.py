from pathlib import Path

import pytest
from django.core.exceptions import ImproperlyConfigured

from config.environment import (
    APPROVED_EMBEDDING_MODEL,
    APPROVED_GROQ_MODEL,
    postgres_database,
    validate_model_identifiers,
    validate_production_environment,
)


ROOT = Path(__file__).resolve().parents[1]


def production_environment(**overrides):
    values = {
        "SECRET_KEY": "test-only-secret",
        "DEBUG": "False",
        "ALLOWED_HOSTS": "pathgen.example",
        "CSRF_TRUSTED_ORIGINS": "https://pathgen.example",
        "DATABASE_URL": "postgresql://user:pass@db.example:5432/pathgen",
        "GROQ_API_KEY": "test-groq-key",
        "GROQ_MODEL": APPROVED_GROQ_MODEL,
        "OPENAI_API_KEY": "test-openai-key",
        "EMBEDDING_MODEL": APPROVED_EMBEDDING_MODEL,
    }
    values.update(overrides)
    return values


def test_env_example_keeps_secret_slots_blank_and_models_exact():
    values = {}
    for raw_line in (ROOT / ".env.example").read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if line and not line.startswith("#"):
            key, value = line.split("=", 1)
            values[key] = value

    assert values == {
        "SECRET_KEY": "",
        "DEBUG": "False",
        "ALLOWED_HOSTS": "",
        "CSRF_TRUSTED_ORIGINS": "",
        "DATABASE_URL": "",
        "GROQ_API_KEY": "",
        "GROQ_MODEL": APPROVED_GROQ_MODEL,
        "OPENAI_API_KEY": "",
        "EMBEDDING_MODEL": APPROVED_EMBEDDING_MODEL,
    }


@pytest.mark.parametrize(
    ("name", "value"),
    [
        ("SECRET_KEY", ""),
        ("DATABASE_URL", ""),
        ("GROQ_API_KEY", ""),
        ("OPENAI_API_KEY", ""),
    ],
)
def test_production_rejects_blank_required_secrets(name, value):
    with pytest.raises(ImproperlyConfigured):
        validate_production_environment(production_environment(**{name: value}))


def test_production_contract_accepts_exact_models_and_postgresql():
    environment = validate_production_environment(production_environment())

    assert environment.groq_model == APPROVED_GROQ_MODEL
    assert environment.embedding_model == APPROVED_EMBEDDING_MODEL
    assert postgres_database(environment.database_url)["ENGINE"] == (
        "django.db.backends.postgresql"
    )


@pytest.mark.parametrize(
    ("groq_model", "embedding_model"),
    [
        ("latest", APPROVED_EMBEDDING_MODEL),
        (APPROVED_GROQ_MODEL, "text-embedding-4"),
    ],
)
def test_model_identifiers_are_exact(groq_model, embedding_model):
    with pytest.raises(ImproperlyConfigured):
        validate_model_identifiers(
            groq_model=groq_model,
            embedding_model=embedding_model,
        )


@pytest.mark.parametrize(
    ("name", "value"),
    [
        ("DEBUG", "True"),
        ("ALLOWED_HOSTS", "*"),
        ("CSRF_TRUSTED_ORIGINS", "http://pathgen.example"),
        ("DATABASE_URL", "sqlite:///pathgen.sqlite3"),
    ],
)
def test_production_rejects_unsafe_environment_values(name, value):
    with pytest.raises(ImproperlyConfigured):
        validate_production_environment(production_environment(**{name: value}))
