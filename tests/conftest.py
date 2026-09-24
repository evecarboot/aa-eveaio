"""Shared fixtures for aa-eveaio tests."""

import pytest


@pytest.fixture(autouse=True)
def _licensed(db):
    """The plugin license-check consults the Django cache first — seeding
    the validated flag exercises the same path a real validation produces
    without touching the license server."""
    from django.core.cache import cache
    cache.set("eveaio_license_valid", True, 3600)
    yield
    cache.clear()


@pytest.fixture()
def user_a(db):
    from django.contrib.auth import get_user_model
    from aa_eveaio.models import EveAioServiceToken
    user = get_user_model().objects.create_user(
        username="alice", password="x")
    token = EveAioServiceToken.objects.create(user=user, token="token-a")
    return user, token.token


@pytest.fixture()
def user_b(db):
    from django.contrib.auth import get_user_model
    from aa_eveaio.models import EveAioServiceToken
    user = get_user_model().objects.create_user(
        username="bob", password="x")
    token = EveAioServiceToken.objects.create(user=user, token="token-b")
    return user, token.token


def api_headers(token):
    return {"HTTP_X_EVEAIO_TOKEN": token}
