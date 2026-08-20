"""Versioned HTTP models for the Bitcoin Math Lab trace API."""
from __future__ import annotations

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, field_validator


HexString = Annotated[
    str,
    StringConstraints(strip_whitespace=True, pattern=r"^(?:[0-9a-fA-F]{2})+$"),
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


class ErrorBody(APIModel):
    code: str
    message: str


class ErrorResponse(APIModel):
    error: ErrorBody
    request_id: str | None = None
