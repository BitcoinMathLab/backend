"""Environment-backed runtime configuration for product integrations."""
from __future__ import annotations

import os
from collections.abc import Mapping
from urllib.parse import urlsplit

from src.database.bitcoin_core_rpc import BitcoinCoreRPC

from bml_backend.bitcoin_core import BitcoinCoreTransactionSource


CORE_VARIABLES = (
    "BML_CORE_RPC_URL",
    "BML_CORE_RPC_COOKIE",
    "BML_CORE_RPC_USER",
    "BML_CORE_RPC_PASSWORD",
    "BML_CORE_RPC_TIMEOUT",
)


def transaction_source_from_environment(
    environment: Mapping[str, str] | None = None,
) -> BitcoinCoreTransactionSource | None:
    """Create the optional Bitcoin Core source, failing fast on partial configuration."""
    values = os.environ if environment is None else environment
    configured = {name: values.get(name, "") for name in CORE_VARIABLES}
    url = configured["BML_CORE_RPC_URL"].strip()
    if not url:
        if any(value.strip() for value in configured.values()):
            raise ValueError("BML_CORE_RPC_URL is required when Bitcoin Core settings are present")
        return None

    parsed = urlsplit(url)
    if (
        parsed.scheme not in {"http", "https"}
        or not parsed.hostname
        or parsed.username is not None
        or parsed.password is not None
        or parsed.query
        or parsed.fragment
    ):
        raise ValueError("BML_CORE_RPC_URL must be an HTTP(S) URL without credentials, query, or fragment")

    cookie = configured["BML_CORE_RPC_COOKIE"].strip() or None
    username = configured["BML_CORE_RPC_USER"].strip() or None
    password = configured["BML_CORE_RPC_PASSWORD"] or None
    if cookie and (username or password):
        raise ValueError("Configure Bitcoin Core with either a cookie or username/password, not both")
    if not cookie and (not username or not password):
        raise ValueError("Bitcoin Core credentials require a cookie or both username and password")

    raw_timeout = configured["BML_CORE_RPC_TIMEOUT"].strip() or "10"
    try:
        timeout = float(raw_timeout)
    except ValueError as exc:
        raise ValueError("BML_CORE_RPC_TIMEOUT must be a positive number") from exc
    if timeout <= 0:
        raise ValueError("BML_CORE_RPC_TIMEOUT must be a positive number")

    client = BitcoinCoreRPC(
        url=url,
        username=username,
        password=password,
        cookie_file=cookie,
        timeout=timeout,
    )
    return BitcoinCoreTransactionSource(client)
