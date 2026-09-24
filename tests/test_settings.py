from django.conf import settings


def test_test_settings_use_postgresql_and_all_domain_packages():
    assert settings.DATABASES["default"]["ENGINE"] == "django.db.backends.postgresql"
    assert {
        "apps.accounts",
        "apps.classrooms",
        "apps.curriculum",
        "apps.learning",
        "apps.adaptive",
        "apps.feedback",
        "apps.core",
    }.issubset(settings.INSTALLED_APPS)


def test_test_settings_keep_provider_models_exact():
    assert settings.GROQ_MODEL == "gpt-oss-120b"
    assert settings.EMBEDDING_MODEL == "text-embedding-3-small"
