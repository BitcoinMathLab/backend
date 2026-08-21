from unittest.mock import Mock, patch

import pytest

from bml_backend.config import transaction_source_from_environment


def test_bitcoin_core_is_optional_when_no_settings_are_present():
    assert transaction_source_from_environment({}) is None


def test_builds_cookie_authenticated_transaction_source():
    client = Mock()
    with patch("bml_backend.config.BitcoinCoreRPC", return_value=client) as client_type:
        source = transaction_source_from_environment(
            {
                "BML_CORE_RPC_URL": "http://127.0.0.1:18332",
                "BML_CORE_RPC_COOKIE": "~/.bitclone/skyscraper.cookie",
                "BML_CORE_RPC_TIMEOUT": "15",
            }
        )

    client_type.assert_called_once_with(
        url="http://127.0.0.1:18332",
        username=None,
        password=None,
        cookie_file="~/.bitclone/skyscraper.cookie",
        timeout=15.0,
    )
    assert source is not None
    assert source._client is client


def test_builds_username_authenticated_transaction_source_without_logging_password():
    with patch("bml_backend.config.BitcoinCoreRPC") as client_type:
        transaction_source_from_environment(
            {
                "BML_CORE_RPC_URL": "https://core.internal/rpc",
                "BML_CORE_RPC_USER": "backend",
                "BML_CORE_RPC_PASSWORD": " private-value ",
            }
        )

    assert client_type.call_args.kwargs["username"] == "backend"
    assert client_type.call_args.kwargs["password"] == " private-value "


@pytest.mark.parametrize(
    "environment, message",
    [
        ({"BML_CORE_RPC_COOKIE": "/cookie"}, "URL is required"),
        ({"BML_CORE_RPC_URL": "ftp://core", "BML_CORE_RPC_COOKIE": "/cookie"}, "HTTP"),
        (
            {
                "BML_CORE_RPC_URL": "http://user:secret@core",
                "BML_CORE_RPC_COOKIE": "/cookie",
            },
            "without credentials",
        ),
        (
            {
                "BML_CORE_RPC_URL": "http://core",
                "BML_CORE_RPC_COOKIE": "/cookie",
                "BML_CORE_RPC_USER": "user",
                "BML_CORE_RPC_PASSWORD": "secret",
            },
            "either a cookie",
        ),
        ({"BML_CORE_RPC_URL": "http://core", "BML_CORE_RPC_USER": "user"}, "credentials"),
        (
            {
                "BML_CORE_RPC_URL": "http://core",
                "BML_CORE_RPC_COOKIE": "/cookie",
                "BML_CORE_RPC_TIMEOUT": "zero",
            },
            "positive number",
        ),
    ],
)
def test_invalid_bitcoin_core_configuration_fails_at_startup(environment, message):
    with pytest.raises(ValueError, match=message):
        transaction_source_from_environment(environment)
