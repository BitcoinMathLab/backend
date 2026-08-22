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


class P2PKHTraceResponse(APIModel):
    api_version: Literal["v1"] = "v1"
    script_type: Literal["P2PKH"] = "P2PKH"
    input_index: int = Field(ge=0)
    scripts: ScriptPairResponse
    trace: ExecutionTraceResponse


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


class TransactionOutputResponse(APIModel):
    vout: int = Field(ge=0, le=0xFFFFFFFF)
    amount_sats: int = Field(ge=0, le=2_100_000_000_000_000)
    script_pubkey_hex: str = Field(pattern=r"^(?:[0-9a-f]{2})*$", max_length=20_000)
    output_type: Literal["P2PK", "P2PKH", "P2MS", "P2SH", "P2WPKH", "P2WSH", "P2TR"] | None


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
