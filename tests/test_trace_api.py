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
P2WPKH_TRANSACTION_HEX = (
    "020000000001013aa815ace3c5751ee6c325d614044ad58c18ed2858a44f9d9f98fbcddad878c1"
    "0000000000ffffffff01344d10000000000016001430cd68883f558464ec7939d9f960956422018f"
    "0702483045022100c7fb3bd38bdceb315a28a0793d85f31e4e1d9983122b4a5de741d6ddca5caf"
    "8202207b2821abd7a1a2157a9d5e69d2fdba3502b0a96be809c34981f8445555bdafdb012103f4"
    "65315805ed271eb972e43d84d2a9e19494d10151d9f6adb32b8534bfd764ab00000000"
)
P2WPKH_LOCKING_SCRIPT_HEX = "0014841b80d2cc75f5345c482af96294d04fdd66b2b7"


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
    assert payload["sources"] == {
        "script_sig": {
            "transaction_txid": "40e331b67c0fe7750bb3b1943b378bf702dce86124dc12fa5980f975db7ec930",
            "index": 0,
        },
        "script_pubkey": {
            "transaction_txid": "0b6461de422c46a221db99608fcbe0326e4f2325ebf2a47c9faf660ed61ee6a4",
            "index": 1,
        },
    }
    assert payload["signature"] == {
        "algorithm": "ECDSA/secp256k1",
        "signature_hex": "3045022100c233c3a8a510e03ad18b0a24694ef00c78101bfd5ac075b8c1037952ce26e91e02205aa5f8f88f29bb4ad5808ebc12abfd26bd791256f367b04c6d955f01f28a7724",
        "public_key_hex": "03f0609c81a45f8cab67fc2d050c21b1acd3d37c7acfd54041be6601ab4cef4f31",
        "sighash_type": 1,
        "sighash_label": "SIGHASH_ALL",
        "preimage_hex": "0100000001a4e61ed60e66af9f7ca4f2eb25234f6e32e0cb8f6099db21a2462c42de61640b010000001976a91455ae51684c43435da751ac8d2173b2652eb6410588acfeffffff02f9243751130000001976a9140c443537e6e31f06e6edb2d4bb80f8481e2831ac88ac14206c00000000001976a914d807ded709af8893f02cdc30a37994429fa248ca88ac751a060001000000",
        "digest_hex": "d21483940571a138f8c768a97f1002cc6b6b0c4df9f647feb513b881162d66e6",
        "valid": True,
    }
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


async def test_trace_known_valid_native_p2wpkh_spend():
    response = await api_request(
        "POST",
        "/api/v1/traces/p2wpkh",
        json={
            "transaction_hex": P2WPKH_TRANSACTION_HEX,
            "input_index": 0,
            "spent_outputs": [{
                "amount_sats": 1_083_200,
                "script_pubkey_hex": P2WPKH_LOCKING_SCRIPT_HEX,
            }],
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["script_type"] == "P2WPKH"
    assert payload["scripts"]["locking"] == P2WPKH_LOCKING_SCRIPT_HEX
    assert payload["scripts"]["script_code"] == (
        "76a914841b80d2cc75f5345c482af96294d04fdd66b2b788ac"
    )
    assert len(payload["scripts"]["witness"]) == 2
    assert payload["signature"] == {
        "algorithm": "ECDSA/secp256k1",
        "signature_hex": payload["scripts"]["witness"][0][:-2],
        "public_key_hex": payload["scripts"]["witness"][1],
        "sighash_type": 1,
        "sighash_label": "SIGHASH_ALL",
        "preimage_hex": payload["signature"]["preimage_hex"],
        "digest_hex": "e4ce544b38c694f09ca943f9a53a9051c981a81177fc0f9d689e2873c5e95270",
        "valid": True,
        "hash_prevouts_hex": "d409ff70f88bfdf4f82f201b99df100cc56466165688acf203d4fd6a7173e8bc",
        "hash_sequence_hex": "3bb13029ce7b1f559ef5e747fcac439f1455a2ec7c5f09b72290795e70665044",
        "hash_outputs_hex": "59d2c073a8f9790f052fe8da122d2de40b1d5646e32f5512e3fb2c46023dd9f4",
        "script_code_hex": "1976a914841b80d2cc75f5345c482af96294d04fdd66b2b788ac",
        "amount_sats": 1_083_200,
    }
    assert payload["trace"]["success"] is True
    assert payload["trace"]["steps"][0]["stacks"]["before"]["main"]["depth"] == 2
    assert [step["opcode"]["name"] for step in payload["trace"]["steps"]] == [
        "OP_DUP", "OP_HASH160", "OP_PUSHBYTES_20", "OP_EQUALVERIFY", "OP_CHECKSIG"
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
            "message": "The request does not match the v1 API contract.",
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
    witness_operation = document["paths"]["/api/v1/traces/p2wpkh"]["post"]
    assert witness_operation["responses"]["200"]["content"]["application/json"]["schema"]["$ref"].endswith(
        "/P2WPKHTraceResponse"
    )
