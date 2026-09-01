"""Versioned HTTP models for the Bitcoin Math Lab trace API."""
from __future__ import annotations

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, field_validator


HexString = Annotated[
    str,
    StringConstraints(strip_whitespace=True, pattern=r"^(?:[0-9a-fA-F]{2})+$"),
]
SpendTypeName = Literal[
    "P2PK",
    "P2PKH",
    "P2SH",
    "P2SH-P2WPKH",
    "P2SH-P2WSH",
    "P2WPKH",
    "P2WSH",
    "P2TR-KEY-PATH",
    "P2TR-SCRIPT-PATH",
    "UNKNOWN",
]


class APIModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class SpentOutputRequest(APIModel):
    amount_sats: int = Field(ge=0, le=2_100_000_000_000_000)
    script_pubkey_hex: HexString = Field(max_length=20_000)

    @field_validator("script_pubkey_hex")
    @classmethod
    def normalize_script_hex(cls, value: str) -> str:
        return value.lower()


class P2PKHTraceRequest(APIModel):
    transaction_hex: HexString = Field(max_length=800_000)
    input_index: int = Field(ge=0)
    spent_outputs: list[SpentOutputRequest] = Field(min_length=1, max_length=1_000)

    @field_validator("transaction_hex")
    @classmethod
    def normalize_transaction_hex(cls, value: str) -> str:
        return value.lower()


class ECDSASignatureVerificationRequest(P2PKHTraceRequest):
    der_signature_hex: HexString = Field(min_length=16, max_length=144)

    @field_validator("der_signature_hex")
    @classmethod
    def normalize_signature_hex(cls, value: str) -> str:
        return value.lower()


class StackSnapshotResponse(APIModel):
    depth: int = Field(ge=0)
    items: list[str]


class OpcodeResponse(APIModel):
    name: str
    value: int = Field(ge=0, le=255)
    hex: str
    byte_offset: int = Field(ge=0)
    byte_length: int = Field(ge=1)
    raw: str
    is_push: bool
    push_data: str | None


class TraceDiagnosticResponse(APIModel):
    code: str
    message: str
    step_index: int | None = Field(default=None, ge=0)
    opcode_name: str | None = None


class StackPairResponse(APIModel):
    main: StackSnapshotResponse
    alt: StackSnapshotResponse


class StepStacksResponse(APIModel):
    before: StackPairResponse
    after: StackPairResponse


class TraceStepResponse(APIModel):
    index: int = Field(ge=0)
    opcode: OpcodeResponse
    stacks: StepStacksResponse
    explanation: str
    diagnostic: TraceDiagnosticResponse | None = None


class ExecutionTraceResponse(APIModel):
    schema_version: Literal[1]
    script: str
    success: bool
    steps: list[TraceStepResponse]
    diagnostic: TraceDiagnosticResponse | None = None


class ScriptPairResponse(APIModel):
    unlocking: str
    locking: str
    combined: str


class ScriptSourceResponse(APIModel):
    transaction_txid: str = Field(pattern=r"^[0-9a-f]{64}$")
    index: int = Field(ge=0, le=0xFFFFFFFF)


class TraceSourcesResponse(APIModel):
    script_sig: ScriptSourceResponse
    script_pubkey: ScriptSourceResponse


class SignatureVerificationResponse(APIModel):
    algorithm: Literal["ECDSA/secp256k1"]
    signature_hex: str = Field(pattern=r"^(?:[0-9a-f]{2})+$")
    public_key_hex: str = Field(pattern=r"^(?:[0-9a-f]{2})+$")
    sighash_type: int = Field(ge=0, le=255)
    sighash_label: str
    preimage_hex: str = Field(pattern=r"^(?:[0-9a-f]{2})+$", max_length=800_008)
    digest_hex: str = Field(pattern=r"^[0-9a-f]{64}$")
    valid: bool


class P2PKHTraceResponse(APIModel):
    api_version: Literal["v1"] = "v1"
    script_type: Literal["P2PKH"] = "P2PKH"
    input_index: int = Field(ge=0)
    scripts: ScriptPairResponse
    sources: TraceSourcesResponse
    signature: SignatureVerificationResponse
    trace: ExecutionTraceResponse


class P2WPKHScriptsResponse(APIModel):
    witness: list[str] = Field(min_length=2, max_length=2)
    locking: str = Field(pattern=r"^0014[0-9a-f]{40}$")
    script_code: str = Field(pattern=r"^76a914[0-9a-f]{40}88ac$")


class P2WPKHTraceSourcesResponse(APIModel):
    witness: ScriptSourceResponse
    script_pubkey: ScriptSourceResponse


class SegwitV0SignatureVerificationResponse(SignatureVerificationResponse):
    hash_prevouts_hex: str = Field(pattern=r"^[0-9a-f]{64}$")
    hash_sequence_hex: str = Field(pattern=r"^[0-9a-f]{64}$")
    hash_outputs_hex: str = Field(pattern=r"^[0-9a-f]{64}$")
    script_code_hex: str = Field(pattern=r"^(?:[0-9a-f]{2})+$")
    amount_sats: int = Field(ge=0, le=2_100_000_000_000_000)


class P2WPKHTraceResponse(APIModel):
    api_version: Literal["v1"] = "v1"
    script_type: Literal["P2WPKH"] = "P2WPKH"
    input_index: int = Field(ge=0)
    scripts: P2WPKHScriptsResponse
    sources: P2WPKHTraceSourcesResponse
    signature: SegwitV0SignatureVerificationResponse
    trace: ExecutionTraceResponse


class ECDSASignatureVerificationResponse(APIModel):
    api_version: Literal["v1"] = "v1"
    script_type: Literal["P2PKH", "P2WPKH"]
    input_index: int = Field(ge=0)
    scripts: ScriptPairResponse | P2WPKHScriptsResponse
    sources: TraceSourcesResponse | P2WPKHTraceSourcesResponse
    signature: SignatureVerificationResponse | SegwitV0SignatureVerificationResponse


class PreviousOutputResponse(APIModel):
    txid: str = Field(pattern=r"^[0-9a-f]{64}$")
    vout: int = Field(ge=0, le=0xFFFFFFFF)
    amount_sats: int = Field(ge=0, le=2_100_000_000_000_000)
    script_pubkey_hex: str = Field(pattern=r"^(?:[0-9a-f]{2})*$", max_length=20_000)
    output_type: Literal["P2PK", "P2PKH", "P2MS", "P2SH", "P2WPKH", "P2WSH", "P2TR"] | None
    spend_type: SpendTypeName
    is_nested: bool
    redeem_script_hex: str | None = Field(
        default=None, pattern=r"^(?:[0-9a-f]{2})+$", max_length=20_000
    )
    script_sig_hex: str = Field(pattern=r"^(?:[0-9a-f]{2})*$", max_length=20_000)
    witness_hex: list[str] = Field(max_length=1_000)


class TransactionOutputResponse(APIModel):
    vout: int = Field(ge=0, le=0xFFFFFFFF)
    amount_sats: int = Field(ge=0, le=2_100_000_000_000_000)
    script_pubkey_hex: str = Field(pattern=r"^(?:[0-9a-f]{2})*$", max_length=20_000)
    output_type: Literal["P2PK", "P2PKH", "P2MS", "P2SH", "P2WPKH", "P2WSH", "P2TR"] | None


class TransactionByteFieldResponse(APIModel):
    id: str = Field(pattern=r"^[a-z0-9]+(?:-[a-z0-9]+)*$", max_length=100)
    label: str = Field(min_length=1, max_length=120)
    group: Literal["header", "input", "output", "witness", "footer"]
    offset: int = Field(ge=0, le=4_000_000)
    length: int = Field(ge=1, le=4_000_000)
    hex: HexString = Field(max_length=8_000_000)
    decoded: str = Field(min_length=1, max_length=200)


class TransactionContextResponse(APIModel):
    api_version: Literal["v1"] = "v1"
    txid: str = Field(pattern=r"^[0-9a-f]{64}$")
    wtxid: str = Field(pattern=r"^[0-9a-f]{64}$")
    transaction_hex: HexString = Field(max_length=800_000)
    version: int = Field(ge=0, le=0xFFFFFFFF)
    locktime: int = Field(ge=0, le=0xFFFFFFFF)
    is_segwit: bool
    is_coinbase: bool
    total_input_sats: int = Field(ge=0, le=2_100_000_000_000_000)
    total_output_sats: int = Field(ge=0, le=2_100_000_000_000_000)
    fee_sats: int | None = Field(default=None, ge=0, le=2_100_000_000_000_000)
    size_bytes: int = Field(ge=0, le=4_000_000)
    weight_units: int = Field(ge=0, le=4_000_000)
    virtual_size_vbytes: int = Field(ge=0, le=1_000_000)
    byte_fields: list[TransactionByteFieldResponse]
    outputs: list[TransactionOutputResponse]
    spent_outputs: list[PreviousOutputResponse]


class TransactionExampleResponse(APIModel):
    slug: str = Field(pattern=r"^[a-z0-9]+(?:-[a-z0-9]+)*$", max_length=80)
    title: str = Field(min_length=1, max_length=100)
    description: str = Field(min_length=1, max_length=240)
    txid: str = Field(pattern=r"^[0-9a-f]{64}$")
    input_count: int = Field(ge=0, le=1_000)
    output_count: int = Field(ge=1, le=1_000)
    expected_spend_types: list[SpendTypeName]
    concepts: list[str] = Field(min_length=1, max_length=10)


class TransactionExamplesResponse(APIModel):
    api_version: Literal["v1"] = "v1"
    examples: list[TransactionExampleResponse]


class StandardScriptTemplateRequest(APIModel):
    template: Literal["P2SH", "P2WPKH", "P2WSH", "P2TR-KEY-PATH", "P2TR-SCRIPT-PATH"]
    program_hex: HexString = Field(max_length=64)

    @field_validator("program_hex")
    @classmethod
    def normalize_program_hex(cls, value: str) -> str:
        return value.lower()


class StandardScriptTemplateResponse(APIModel):
    api_version: Literal["v1"] = "v1"
    template: Literal["P2SH", "P2WPKH", "P2WSH", "P2TR-KEY-PATH", "P2TR-SCRIPT-PATH"]
    script_type: Literal["P2SH", "P2WPKH", "P2WSH", "P2TR"]
    program_hex: HexString = Field(max_length=64)
    script_pubkey_hex: HexString = Field(max_length=68)
    address: str = Field(min_length=1, max_length=100)


class ErrorBody(APIModel):
    code: str
    message: str


class ErrorResponse(APIModel):
    error: ErrorBody
    request_id: str | None = None
