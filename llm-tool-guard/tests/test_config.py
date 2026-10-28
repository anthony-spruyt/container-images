"""Tests for environment configuration."""

import math
import re
import secrets

import pytest

from config import Settings


def test_optional_features_are_off_until_configured():
    settings = Settings.from_env({})

    assert settings.jev_mode == "off"
    assert settings.valkey_url == ""
    assert settings.auth_token == ""


def test_the_default_body_limit_exceeds_the_default_text_limit():
    settings = Settings.from_env({})

    assert settings.max_body_bytes > settings.max_text_bytes


def test_the_scanner_runs_on_the_gpu_unless_told_otherwise():
    assert Settings.from_env({}).scanner_device == "GPU"
    assert Settings.from_env({"SCANNER_DEVICE": ""}).scanner_device == "GPU"
    assert Settings.from_env({"SCANNER_DEVICE": "CPU"}).scanner_device == "CPU"


def test_the_default_jev_model_is_a_pinned_version():
    assert re.fullmatch(r"jev-\d+\.\d+\.\d+", Settings.from_env({}).jev_model)


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


JEV_ENFORCE = {"JEV_MODE": "enforce", "JEV_API_URL": "https://jev.test", "JEV_API_KEY": "key"}


def test_jev_overrides():
    settings = Settings.from_env(
        {
            **JEV_ENFORCE,
            "JEV_API_URL": "https://jev.test/jev/",
            "JEV_MODEL": "jev-9.9.9",
            "JEV_BLOCK_AT": "0.95",
            "JEV_CLEAR_BELOW": "0.05",
            "JEV_TIMEOUT_SECONDS": "2.5",
            "JEV_MAX_TEXT_BYTES": "4096",
            "JEV_MAX_WINDOWS": "5",
        }
    )

    assert settings.jev_mode == "enforce"
    assert settings.jev_api_key == "key"
    assert settings.jev_api_url == "https://jev.test/jev"
    assert settings.jev_model == "jev-9.9.9"
    assert (settings.jev_block_at, settings.jev_clear_below) == (0.95, 0.05)
    assert settings.jev_timeout_seconds == 2.5
    assert settings.jev_max_text_bytes == 4096
    assert settings.jev_max_windows == 5


def test_the_default_jev_window_cap_fits_in_the_default_pending_limit():
    settings = Settings.from_env({})

    assert 1 <= settings.jev_max_windows <= settings.max_pending_scans


def test_jev_enforce_without_a_key_fails_at_load():
    with pytest.raises(ValueError, match="JEV_API_KEY"):
        Settings.from_env({"JEV_MODE": "enforce", "JEV_API_URL": "https://jev.test"})


def test_jev_enforce_without_a_url_fails_at_load():
    with pytest.raises(ValueError, match="JEV_API_URL"):
        Settings.from_env({"JEV_MODE": "enforce", "JEV_API_KEY": "key"})


def test_jev_off_needs_no_url_or_key():
    settings = Settings.from_env({"JEV_MODE": "off"})

    assert (settings.jev_api_url, settings.jev_api_key) == ("", "")


@pytest.mark.parametrize("mode", ["off", "enforce"])
@pytest.mark.parametrize("key", ["s3cr3t\n", "s3cr3t\r\n", " s3cr3t", "s3c r3t", "s3c\tr3t", "s3cr3té", "s3cr3t\x00"])
def test_a_key_that_is_not_printable_ascii_fails_at_load_without_echoing_it(mode, key):
    with pytest.raises(ValueError, match="JEV_API_KEY") as caught:
        Settings.from_env({"JEV_MODE": mode, "JEV_API_KEY": key})

    assert "s3c" not in str(caught.value)
    assert "r3t" not in str(caught.value)


def test_a_key_of_printable_ascii_is_accepted():
    key = "ts_Abc-123.xyz~!#"

    assert Settings.from_env({**JEV_ENFORCE, "JEV_API_KEY": key}).jev_api_key == key


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
        ("JEV_MAX_WINDOWS", "0"),
        ("JEV_MAX_WINDOWS", "-1"),
        ("JEV_MAX_WINDOWS", "x"),
        ("JEV_MAX_WINDOWS", "2.5"),
        ("JEV_API_URL", "jev.test"),
        ("JEV_API_URL", "ftp://jev.test"),
        ("JEV_API_URL", "https://"),
        ("JEV_API_URL", "https:///jev"),
        ("JEV_API_URL", "http://[::1"),
        ("JEV_API_URL", "http://jev.test:abc"),
        ("JEV_API_URL", "http://jev.test:99999"),
        ("JEV_API_URL", "http://jev.test:0"),
        ("JEV_API_URL", "https://jev.test/jev?x=1"),
        ("JEV_API_URL", "https://jev.test/jev#top"),
        ("JEV_API_URL", "https://jev.test?"),
        ("JEV_API_URL", "https://jev.test#"),
        ("JEV_API_URL", "https://u:pw@jev.test"),
        ("JEV_API_URL", "https://@jev.test"),
        ("JEV_API_URL", "https://jev.test "),
        ("JEV_API_URL", " https://jev.test"),
        ("JEV_API_URL", "https://jev.test\n"),
        ("JEV_API_URL", "https://jev.te\tst"),
    ],
)
def test_invalid_jev_values_are_rejected_by_name(name, value):
    with pytest.raises(ValueError, match=name):
        Settings.from_env({**JEV_ENFORCE, name: value})


@pytest.mark.parametrize("scheme", ["ftp", "https"])
@pytest.mark.parametrize("user_info", ["user:{secret}", "{secret}"])
def test_a_rejected_url_is_not_echoed(scheme, user_info):
    secret = secrets.token_hex(8)
    url = f"{scheme}://{user_info.format(secret=secret)}@jev.test"

    with pytest.raises(ValueError, match="JEV_API_URL") as caught:
        Settings.from_env({**JEV_ENFORCE, "JEV_API_URL": url})

    assert secret not in str(caught.value)
    assert "jev.test" not in str(caught.value)


@pytest.mark.parametrize(
    ("url", "expected"),
    [
        ("https://jev.test", "https://jev.test"),
        ("https://jev.test/", "https://jev.test"),
        ("https://jev.test/jev", "https://jev.test/jev"),
        ("https://jev.test/jev/", "https://jev.test/jev"),
        ("http://jev.svc:4000/a/b//", "http://jev.svc:4000/a/b"),
        ("http://jev.test:1", "http://jev.test:1"),
        ("https://jev.test/a@b", "https://jev.test/a@b"),
    ],
)
def test_the_url_loses_its_trailing_slashes_and_keeps_its_path_prefix(url, expected):
    assert Settings.from_env({**JEV_ENFORCE, "JEV_API_URL": url}).jev_api_url == expected


def test_repr_hides_the_jev_key():
    key = secrets.token_hex(8)

    assert key not in repr(Settings.from_env({**JEV_ENFORCE, "JEV_API_KEY": key}))
