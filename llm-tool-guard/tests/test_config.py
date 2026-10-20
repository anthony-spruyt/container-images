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
    assert settings.max_body_bytes == 8 * 1024 * 1024
    assert settings.max_concurrent_requests == 8
    assert settings.scan_timeout_seconds == 300
    assert settings.shutdown_drain_seconds == 20
    assert settings.jev_mode == "off"
    assert settings.typesafe_api_base == "https://api.typesafe.ai"
    assert settings.jev_model == "jev-1.13.0"
    assert (settings.jev_block_at, settings.jev_clear_below) == (0.90, 0.08)
    assert settings.jev_timeout_seconds == 10
    assert settings.jev_max_text_bytes == 16384


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
            "MAX_CONCURRENT_REQUESTS": "3",
            "SCAN_TIMEOUT_SECONDS": "12.5",
            "SHUTDOWN_DRAIN_SECONDS": "0",
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
    assert settings.max_concurrent_requests == 3
    assert settings.scan_timeout_seconds == 12.5
    assert settings.shutdown_drain_seconds == 0
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
        ("MAX_CONCURRENT_REQUESTS", "0"),
        ("SCAN_TIMEOUT_SECONDS", "0"),
        ("SHUTDOWN_DRAIN_SECONDS", "-1"),
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


JEV_ENFORCE = {"JEV_MODE": "enforce", "TYPESAFE_API_KEY": "key"}


def test_jev_overrides():
    settings = Settings.from_env(
        {
            **JEV_ENFORCE,
            "TYPESAFE_API_BASE": "https://typesafe.example/",
            "JEV_MODEL": "jev-9.9.9",
            "JEV_BLOCK_AT": "0.95",
            "JEV_CLEAR_BELOW": "0.05",
            "JEV_TIMEOUT_SECONDS": "2.5",
            "JEV_MAX_TEXT_BYTES": "4096",
        }
    )

    assert settings.jev_mode == "enforce"
    assert settings.typesafe_api_key == "key"
    assert settings.typesafe_api_base == "https://typesafe.example"
    assert settings.jev_model == "jev-9.9.9"
    assert (settings.jev_block_at, settings.jev_clear_below) == (0.95, 0.05)
    assert settings.jev_timeout_seconds == 2.5
    assert settings.jev_max_text_bytes == 4096


def test_jev_enforce_without_a_key_fails_at_load():
    with pytest.raises(ValueError, match="TYPESAFE_API_KEY"):
        Settings.from_env({"JEV_MODE": "enforce"})


def test_jev_off_needs_no_key():
    assert Settings.from_env({"JEV_MODE": "off"}).typesafe_api_key == ""


def test_jev_clear_below_may_not_exceed_block_at():
    with pytest.raises(ValueError, match="JEV_CLEAR_BELOW"):
        Settings.from_env({"JEV_CLEAR_BELOW": "0.5", "JEV_BLOCK_AT": "0.4"})


def test_jev_thresholds_are_checked_even_when_off():
    with pytest.raises(ValueError, match="JEV_CLEAR_BELOW"):
        Settings.from_env({"JEV_MODE": "off", "JEV_CLEAR_BELOW": "0.95"})


def test_jev_thresholds_may_meet():
    settings = Settings.from_env({"JEV_CLEAR_BELOW": "0.5", "JEV_BLOCK_AT": "0.5"})

    assert settings.jev_clear_below == settings.jev_block_at == 0.5


@pytest.mark.parametrize(
    ("name", "value"),
    [
        ("JEV_MODE", "shadow"),
        ("JEV_MODE", "ENFORCE"),
        ("JEV_BLOCK_AT", "0"),
        ("JEV_BLOCK_AT", "1.5"),
        ("JEV_BLOCK_AT", "nan"),
        ("JEV_CLEAR_BELOW", "-0.1"),
        ("JEV_CLEAR_BELOW", "x"),
        ("JEV_TIMEOUT_SECONDS", "0"),
        ("JEV_MAX_TEXT_BYTES", "0"),
        ("TYPESAFE_API_BASE", "api.typesafe.ai"),
        ("TYPESAFE_API_BASE", "ftp://api.typesafe.ai"),
    ],
)
def test_invalid_jev_values_are_rejected_by_name(name, value):
    with pytest.raises(ValueError, match=name):
        Settings.from_env({**JEV_ENFORCE, name: value})


def test_repr_hides_the_typesafe_key():
    key = secrets.token_hex(8)

    assert key not in repr(Settings.from_env({"JEV_MODE": "enforce", "TYPESAFE_API_KEY": key}))
