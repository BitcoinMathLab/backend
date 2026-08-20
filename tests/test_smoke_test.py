import pytest

from scripts.smoke_test import SmokeTestError, TRANSACTION_HEX, trace_request, validate_trace


def response(*, success=True, opcode_names=None):
    names = opcode_names or [
        "OP_PUSHBYTES_72",
        "OP_PUSHBYTES_33",
        "OP_DUP",
        "OP_HASH160",
        "OP_PUSHBYTES_20",
        "OP_EQUALVERIFY",
        "OP_CHECKSIG",
    ]
    return {
        "api_version": "v1",
        "trace": {
            "schema_version": 1,
            "success": success,
            "steps": [{"opcode": {"name": name}} for name in names],
        },
    }


def test_curated_smoke_request_changes_only_the_intended_signature_byte():
    valid = trace_request(TRANSACTION_HEX)
    invalid = trace_request(TRANSACTION_HEX.replace("c233", "c333", 1))

    assert valid["spent_outputs"] == invalid["spent_outputs"]
    assert valid["transaction_hex"] != invalid["transaction_hex"]
    assert len(valid["transaction_hex"]) == len(invalid["transaction_hex"])


def test_trace_validator_accepts_expected_valid_and_invalid_contracts():
    validate_trace(response(success=True), expected_success=True)
    validate_trace(response(success=False), expected_success=False)


@pytest.mark.parametrize(
    "payload, expected_success",
    [
        ({}, True),
        (response(success=False), True),
        (response(opcode_names=["OP_DUP"]), True),
    ],
)
def test_trace_validator_rejects_contract_drift(payload, expected_success):
    with pytest.raises(SmokeTestError):
        validate_trace(payload, expected_success=expected_success)
