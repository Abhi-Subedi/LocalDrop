from __future__ import annotations

import conftest


def test_test_database_url_prefers_ci_override(monkeypatch):
    monkeypatch.setenv(
        "LOCALDROP_TEST_DATABASE_URL",
        "postgresql+psycopg://ci-user@127.0.0.1:5433/localdrop_test",
    )
    assert (
        conftest._test_database_url()
        == "postgresql+psycopg://ci-user@127.0.0.1:5433/localdrop_test"
    )


def test_test_database_url_uses_local_default_when_override_missing(monkeypatch):
    monkeypatch.delenv("LOCALDROP_TEST_DATABASE_URL", raising=False)
    assert (
        conftest._test_database_url()
        == "postgresql+psycopg://postgres@127.0.0.1:5433/localdrop_test"
    )
