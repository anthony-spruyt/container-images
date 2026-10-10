"""Tests for environment configuration."""

import math
import secrets

import pytest

from config import Settings


def test_defaults():
    settings = Settings.from_env({})

    assert settings.listen_port == 8080
    assert settings.model == "Horizon-Labs/prompt-injection-guard-base"
    assert settings.injection_label == "INJECTION"
    assert settings.valkey_url == ""
    assert settings.auth_token == ""
    assert settings.max_text_bytes >= 256 * 1024
    assert settings.cache_ttl_seconds >= 30 * 24 * 3600
    assert settings.scan_workers == 1
    assert settings.threshold == 0.9
    assert (settings.window_tokens, settings.window_overlap) == (2048, 512)
    assert settings.max_windows == 171


def test_overrides():
    settings = Settings.from_env(
        {
            "LISTEN_PORT": "9000",
            "THRESHOLD": "0.75",
            "WINDOW_TOKENS": "4096",
            "WINDOW_OVERLAP": "256",
            "WINDOW_BATCH_SIZE": "2",
            "MAX_WINDOWS": "10",
            "MAX_TEXT_BYTES": "1000",
            "MAX_BODY_BYTES": "5000",
            "SCAN_WORKERS": "3",
            "MAX_PENDING_SCANS": "7",
            "VALKEY_URL": "redis://valkey:6379/2",
            "VALKEY_USERNAME": "guard",
            "VALKEY_PASSWORD": "pw",
            "VALKEY_TIMEOUT_SECONDS": "0.25",
            "CACHE_TTL_SECONDS": "60",
            "AUTH_TOKEN": "tok",
        }
    )

    assert settings.listen_port == 9000
    assert settings.threshold == 0.75
    assert (settings.window_tokens, settings.window_overlap, settings.window_batch_size) == (4096, 256, 2)
    assert settings.max_windows == 10
    assert (settings.max_text_bytes, settings.max_body_bytes) == (1000, 5000)
    assert (settings.scan_workers, settings.max_pending_scans) == (3, 7)
    assert (settings.valkey_url, settings.valkey_username, settings.valkey_password) == (
        "redis://valkey:6379/2",
        "guard",
        "pw",
    )
    assert settings.valkey_timeout_seconds == 0.25
    assert settings.cache_ttl_seconds == 60
    assert settings.auth_token == "tok"


def test_empty_values_use_defaults():
    assert Settings.from_env({"THRESHOLD": "", "SCAN_WORKERS": ""}) == Settings.from_env({})


@pytest.mark.parametrize(
    ("name", "value"),
    [
        ("LISTEN_PORT", "http"),
        ("SCAN_WORKERS", "0"),
        ("MAX_TEXT_BYTES", "-1"),
        ("MAX_PENDING_SCANS", "1.5"),
        ("CACHE_TTL_SECONDS", "0"),
        ("WINDOW_TOKENS", "1"),
        ("WINDOW_OVERLAP", "-1"),
        ("MAX_WINDOWS", "0"),
        ("THRESHOLD", "0"),
        ("THRESHOLD", "1.5"),
        ("THRESHOLD", "nan"),
        ("VALKEY_TIMEOUT_SECONDS", "0"),
    ],
)
def test_invalid_values_are_rejected_by_name(name, value):
    with pytest.raises(ValueError, match=name):
        Settings.from_env({name: value})


def test_overlap_must_leave_room_in_the_window():
    with pytest.raises(ValueError, match="WINDOW_OVERLAP"):
        Settings.from_env({"WINDOW_TOKENS": "512", "WINDOW_OVERLAP": "512"})


def test_max_windows_defaults_to_covering_max_text_bytes_at_one_token_per_byte():
    settings = Settings.from_env({"WINDOW_TOKENS": "1026", "WINDOW_OVERLAP": "24", "MAX_TEXT_BYTES": "100000"})

    span = 1026 - 2
    assert settings.max_windows == 1 + math.ceil((100000 - span) / (span - 24))


def test_max_windows_default_is_one_for_text_that_fits_one_window():
    assert Settings.from_env({"WINDOW_TOKENS": "4096", "MAX_TEXT_BYTES": "100"}).max_windows == 1


def test_repr_hides_secrets():
    url_password, password, token = (secrets.token_hex(8) for _ in range(3))
    settings = Settings.from_env(
        {"VALKEY_URL": f"redis://:{url_password}@valkey:6379", "VALKEY_PASSWORD": password, "AUTH_TOKEN": token}
    )

    for secret in (url_password, password, token):
        assert secret not in repr(settings)
