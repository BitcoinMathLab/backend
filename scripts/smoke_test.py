#!/usr/bin/env python3
"""Exercise the public MVP contract against a running Bitcoin Math Lab API."""
from __future__ import annotations

import argparse
import json
import time
from typing import Any
from urllib.error import HTTPError
from urllib.request import Request, urlopen


TRANSACTION_HEX = (
    "0100000001a4e61ed60e66af9f7ca4f2eb25234f6e32e0cb8f6099db21a2462c42de61640b010000006b"
    "483045022100c233c3a8a510e03ad18b0a24694ef00c78101bfd5ac075b8c1037952ce26e91e02205aa5f8f88f29bb"
    "4ad5808ebc12abfd26bd791256f367b04c6d955f01f28a7724012103f0609c81a45f8cab67fc2d050c21b1acd3d37c"
    "7acfd54041be6601ab4cef4f31feffffff02f9243751130000001976a9140c443537e6e31f06e6edb2d4bb80f8481e"
    "2831ac88ac14206c00000000001976a914d807ded709af8893f02cdc30a37994429fa248ca88ac751a0600"
)
LOCKING_SCRIPT_HEX = "76a91455ae51684c43435da751ac8d2173b2652eb6410588ac"


class SmokeTestError(RuntimeError):
    """Raised when the deployed API does not satisfy the MVP contract."""


def trace_request(transaction_hex: str) -> dict[str, Any]:
    return {
        "transaction_hex": transaction_hex,
        "input_index": 0,
        "spent_outputs": [
            {
                "amount_sats": 82_974_043_165,
                "script_pubkey_hex": LOCKING_SCRIPT_HEX,
            }
        ],
    }


def request_json(
    url: str, *, payload: dict[str, Any] | None = None, timeout: float = 5
) -> tuple[dict[str, Any], str]:
    body = None if payload is None else json.dumps(payload).encode("utf-8")
    request = Request(
        url,
        data=body,
        headers={"Content-Type": "application/json"} if body is not None else {},
        method="POST" if body is not None else "GET",
    )
    try:
        with urlopen(request, timeout=timeout) as response:
            result = json.load(response)
            request_id = response.headers.get("X-Request-ID", "")
    except HTTPError as exc:
        raise SmokeTestError(f"{url} returned HTTP {exc.code}") from exc
    except (OSError, json.JSONDecodeError) as exc:
        raise SmokeTestError(f"{url} did not return a JSON response") from exc

    if len(request_id) != 32:
        raise SmokeTestError(f"{url} did not return a valid X-Request-ID")
    return result, request_id


def wait_until_ready(api_base_url: str, timeout: float = 30) -> dict[str, Any]:
    deadline = time.monotonic() + timeout
    health_url = f"{api_base_url}/api/v1/health"
    while True:
        try:
            health, _request_id = request_json(health_url, timeout=2)
            if health.get("status") == "ok":
                return health
        except SmokeTestError:
            pass
        if time.monotonic() >= deadline:
            raise SmokeTestError(f"API was not ready after {timeout:g} seconds")
        time.sleep(0.5)


def validate_trace(payload: dict[str, Any], *, expected_success: bool) -> None:
    try:
        trace = payload["trace"]
        opcode_names = [step["opcode"]["name"] for step in trace["steps"]]
    except (KeyError, TypeError) as exc:
        raise SmokeTestError("Trace response does not match the v1 structure") from exc

    if payload.get("api_version") != "v1" or trace.get("schema_version") != 1:
        raise SmokeTestError("Trace response version is not v1/schema 1")
    if trace.get("success") is not expected_success:
        raise SmokeTestError(f"Expected trace success={expected_success}")
    if opcode_names != [
        "OP_PUSHBYTES_72",
        "OP_PUSHBYTES_33",
        "OP_DUP",
        "OP_HASH160",
        "OP_PUSHBYTES_20",
        "OP_EQUALVERIFY",
        "OP_CHECKSIG",
    ]:
        raise SmokeTestError("Trace did not execute the expected seven P2PKH steps")


def run_smoke_test(api_base_url: str) -> None:
    api_base_url = api_base_url.rstrip("/")
    health = wait_until_ready(api_base_url)
    trace_url = f"{api_base_url}/api/v1/traces/p2pkh"

    valid, valid_request_id = request_json(trace_url, payload=trace_request(TRANSACTION_HEX))
    validate_trace(valid, expected_success=True)

    invalid_hex = TRANSACTION_HEX.replace("c233", "c333", 1)
    invalid, invalid_request_id = request_json(trace_url, payload=trace_request(invalid_hex))
    validate_trace(invalid, expected_success=False)

    print(
        json.dumps(
            {
                "status": "passed",
                "api_version": health.get("version"),
                "valid_request_id": valid_request_id,
                "invalid_request_id": invalid_request_id,
            },
            separators=(",", ":"),
        )
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--api-base-url", required=True)
    args = parser.parse_args()
    try:
        run_smoke_test(args.api_base_url)
    except SmokeTestError as exc:
        parser.exit(1, f"Smoke test failed: {exc}\n")


if __name__ == "__main__":
    main()
