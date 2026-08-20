import httpx
import pytest

from bml_backend.app import app
from src.tx import Tx


TRANSACTION_HEX = (
    "0100000001a4e61ed60e66af9f7ca4f2eb25234f6e32e0cb8f6099db21a2462c42de61640b010000006b"
    "483045022100c233c3a8a510e03ad18b0a24694ef00c78101bfd5ac075b8c1037952ce26e91e02205aa5f8f88f29bb"
    "4ad5808ebc12abfd26bd791256f367b04c6d955f01f28a7724012103f0609c81a45f8cab67fc2d050c21b1acd3d37c"
    "7acfd54041be6601ab4cef4f31feffffff02f9243751130000001976a9140c443537e6e31f06e6edb2d4bb80f8481e"
    "2831ac88ac14206c00000000001976a914d807ded709af8893f02cdc30a37994429fa248ca88ac751a0600"
)
LOCKING_SCRIPT_HEX = "76a91455ae51684c43435da751ac8d2173b2652eb6410588ac"


def request_body(*, transaction_hex=TRANSACTION_HEX, locking_script_hex=LOCKING_SCRIPT_HEX):
    return {
        "transaction_hex": transaction_hex,
        "input_index": 0,
        "spent_outputs": [
            {
                "amount_sats": 82_974_043_165,
                "script_pubkey_hex": locking_script_hex,
            }
        ],
    }


pytestmark = pytest.mark.anyio


@pytest.fixture
def anyio_backend():
    return "asyncio"


async def api_request(method: str, path: str, *, json=None):
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        return await client.request(method, path, json=json)


async def test_health_endpoint():
    response = await api_request("GET", "/api/v1/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok", "version": "0.1.0"}


async def test_trace_known_valid_p2pkh_spend():
    response = await api_request("POST", "/api/v1/traces/p2pkh", json=request_body())

    assert response.status_code == 200
    payload = response.json()
    assert payload["api_version"] == "v1"
    assert payload["script_type"] == "P2PKH"
    assert payload["input_index"] == 0
    assert payload["scripts"]["locking"] == LOCKING_SCRIPT_HEX
    assert payload["scripts"]["combined"] == payload["trace"]["script"]
    assert payload["trace"]["schema_version"] == 1
    assert payload["trace"]["success"] is True
    assert payload["trace"]["diagnostic"] is None
    assert [step["opcode"]["name"] for step in payload["trace"]["steps"]] == [
        "OP_PUSHBYTES_72",
        "OP_PUSHBYTES_33",
        "OP_DUP",
        "OP_HASH160",
        "OP_PUSHBYTES_20",
        "OP_EQUALVERIFY",
        "OP_CHECKSIG",
    ]


async def test_invalid_signature_is_a_normal_failure_trace():
    tx = Tx.from_bytes(bytes.fromhex(TRANSACTION_HEX))
    scriptsig = bytearray(tx.inputs[0].scriptsig)
    scriptsig[10] ^= 0x01
    tx.inputs[0].scriptsig = bytes(scriptsig)

    response = await api_request(
        "POST",
        "/api/v1/traces/p2pkh",
        json=request_body(transaction_hex=tx.to_bytes().hex()),
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["trace"]["success"] is False
    assert payload["trace"]["diagnostic"]["code"] == "false-final-value"
    assert "exception_type" not in str(payload)


async def test_request_validation_has_stable_safe_shape():
    response = await api_request(
        "POST",
        "/api/v1/traces/p2pkh",
        json=request_body(transaction_hex="not hex"),
    )

    assert response.status_code == 422
    assert response.json() == {
        "error": {
            "code": "request-validation",
            "message": "The request body does not match the v1 trace contract.",
        }
    }


async def test_spent_output_count_must_match_transaction_inputs():
    body = request_body()
    body["spent_outputs"].append(body["spent_outputs"][0])

    response = await api_request("POST", "/api/v1/traces/p2pkh", json=body)

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "spent-output-count"


async def test_input_index_must_identify_transaction_input():
    body = request_body()
    body["input_index"] = 1

    response = await api_request("POST", "/api/v1/traces/p2pkh", json=body)

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "input-index-out-of-range"


async def test_transaction_must_not_contain_trailing_bytes():
    response = await api_request(
        "POST",
        "/api/v1/traces/p2pkh",
        json=request_body(transaction_hex=TRANSACTION_HEX + "00"),
    )

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "invalid-transaction"


async def test_invalid_p2pkh_unlocking_script_is_rejected():
    tx = Tx.from_bytes(bytes.fromhex(TRANSACTION_HEX))
    tx.inputs[0].scriptsig += b"\x51"

    response = await api_request(
        "POST",
        "/api/v1/traces/p2pkh",
        json=request_body(transaction_hex=tx.to_bytes().hex()),
    )

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "invalid-unlocking-script"


async def test_non_p2pkh_spent_output_is_rejected():
    response = await api_request(
        "POST",
        "/api/v1/traces/p2pkh",
        json=request_body(locking_script_hex="51"),
    )

    assert response.status_code == 422
    assert response.json()["error"] == {
        "code": "unsupported-script-type",
        "message": "Selected spent output is not a legacy P2PKH script",
    }


async def test_openapi_publishes_versioned_trace_contract():
    response = await api_request("GET", "/api/v1/openapi.json")

    assert response.status_code == 200
    document = response.json()
    operation = document["paths"]["/api/v1/traces/p2pkh"]["post"]
    assert operation["responses"]["200"]["content"]["application/json"]["schema"]["$ref"].endswith(
        "/P2PKHTraceResponse"
    )
    assert operation["responses"]["422"]["content"]["application/json"]["schema"]["$ref"].endswith(
        "/ErrorResponse"
    )
