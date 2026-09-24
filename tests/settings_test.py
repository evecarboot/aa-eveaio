"""Minimal Django settings for aa-eveaio tests.

Runs the real plugin models/views/URLs without an AllianceAuth install —
every allianceauth import in the plugin is already lazy, so the plain
Django stack is sufficient. A file-backed SQLite DB is used so threaded
tests and the in-process live server share one store.
"""

import os
import tempfile

SECRET_KEY = "aa-eveaio-test-key-not-a-secret"
DEBUG = True
USE_TZ = True

INSTALLED_APPS = [
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "aa_eveaio",
]

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        # A real file so concurrent connections (threaded live server,
        # concurrency tests) share one database.
        "NAME": os.environ.get(
            "AA_EVEAIO_TEST_DB",
            os.path.join(tempfile.gettempdir(), "aa_eveaio_test.sqlite3"),
        ),
        "OPTIONS": {"timeout": 30},
    }
}

ROOT_URLCONF = "tests.urls_test"

DEFAULT_AUTO_FIELD = "django.db.models.AutoField"

CACHES = {
    "default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"}
}

PASSWORD_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]

# Keep test runs quiet; views must never log secrets regardless.
LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "handlers": {"console": {"class": "logging.StreamHandler"}},
    "root": {"handlers": ["console"], "level": "WARNING"},
}
