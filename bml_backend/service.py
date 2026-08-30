"""Product orchestration around Bitclone's transport-neutral trace engine."""
from __future__ import annotations

from dataclasses import dataclass

from src.script import (
    P2PKHTraceResult,
    get_legacy_sighash,
    get_legacy_sighash_preimage,
    trace_p2pkh_spend,
    verify_ecdsa_sig,
)
from src.tx import Tx, UTXO

from bml_backend.models import (
    ExecutionTraceResponse,
    OpcodeResponse,
    P2PKHTraceRequest,
    P2PKHTraceResponse,
    ScriptPairResponse,
    ScriptSourceResponse,
    SignatureVerificationResponse,
    StackPairResponse,
    StackSnapshotResponse,
    StepStacksResponse,
    TraceDiagnosticResponse,
    TraceStepResponse,
    TraceSourcesResponse,
)


@dataclass(frozen=True, slots=True)
class TraceRequestError(Exception):
    code: str
    message: str

    def __str__(self) -> str:
        return self.message


def _diagnostic_response(diagnostic) -> TraceDiagnosticResponse | None:
    if diagnostic is None:
        return None
    return TraceDiagnosticResponse(
        code=diagnostic.code,
        message=diagnostic.message,
        step_index=diagnostic.step_index,
        opcode_name=diagnostic.opcode_name,
    )


def _snapshot_response(snapshot) -> StackSnapshotResponse:
    return StackSnapshotResponse(
        depth=snapshot.depth,
        items=[item.hex() for item in snapshot.items],
    )


def _sighash_label(value: int) -> str:
    return {1: "SIGHASH_ALL", 2: "SIGHASH_NONE", 3: "SIGHASH_SINGLE"}.get(
        value & 0x1F, f"SIGHASH_{value:02X}"
    ) + (" | ANYONECANPAY" if value & 0x80 else "")


def _signature_response(result: P2PKHTraceResult, tx: Tx) -> SignatureVerificationResponse:
    pushes = [step.opcode.push_data for step in result.trace.steps if step.opcode.is_push]
    if len(pushes) < 2 or not pushes[0] or not pushes[1]:
        raise TraceRequestError("invalid-unlocking-script", "P2PKH scriptSig must push a signature and public key.")

    signature_with_type = pushes[0] if isinstance(pushes[0], bytes) else bytes.fromhex(pushes[0])
    public_key = pushes[1] if isinstance(pushes[1], bytes) else bytes.fromhex(pushes[1])
    sighash_type = signature_with_type[-1]
    digest = get_legacy_sighash(
        tx, result.input_index, result.locking_script, sighash_type
    )
    preimage = get_legacy_sighash_preimage(
        tx, result.input_index, result.locking_script, sighash_type
    )
    return SignatureVerificationResponse(
        algorithm="ECDSA/secp256k1",
        signature_hex=signature_with_type[:-1].hex(),
        public_key_hex=public_key.hex(),
        sighash_type=sighash_type,
        sighash_label=_sighash_label(sighash_type),
        preimage_hex=preimage.hex(),
        digest_hex=digest.hex(),
        valid=verify_ecdsa_sig(signature_with_type[:-1], digest, public_key),
    )


def _result_response(result: P2PKHTraceResult, tx: Tx) -> P2PKHTraceResponse:
    steps = []
    for step in result.trace.steps:
        steps.append(TraceStepResponse(
            index=step.index,
            opcode=OpcodeResponse(**step.opcode.to_dict()),
            stacks=StepStacksResponse(
                before=StackPairResponse(
                    main=_snapshot_response(step.main_stack_before),
                    alt=_snapshot_response(step.alt_stack_before),
                ),
                after=StackPairResponse(
                    main=_snapshot_response(step.main_stack_after),
                    alt=_snapshot_response(step.alt_stack_after),
                ),
            ),
            explanation=step.explanation,
            diagnostic=_diagnostic_response(step.diagnostic),
        ))

    return P2PKHTraceResponse(
        input_index=result.input_index,
        scripts=ScriptPairResponse(
            unlocking=result.unlocking_script.hex(),
            locking=result.locking_script.hex(),
            combined=result.combined_script.hex(),
        ),
        sources=TraceSourcesResponse(
            script_sig=ScriptSourceResponse(
                transaction_txid=tx.txid[::-1].hex(), index=result.input_index
            ),
            script_pubkey=ScriptSourceResponse(
                transaction_txid=tx.inputs[result.input_index].txid[::-1].hex(),
                index=tx.inputs[result.input_index].vout,
            ),
        ),
        signature=_signature_response(result, tx),
        trace=ExecutionTraceResponse(
            schema_version=result.trace.SCHEMA_VERSION,
            script=result.trace.script.hex(),
            success=bool(result.trace.success),
            steps=steps,
            diagnostic=_diagnostic_response(result.trace.diagnostic),
        ),
    )


def execute_p2pkh_trace(request: P2PKHTraceRequest) -> P2PKHTraceResponse:
    raw_transaction = bytes.fromhex(request.transaction_hex)
    try:
        tx = Tx.from_bytes(raw_transaction)
    except Exception as exc:
        raise TraceRequestError(
            "invalid-transaction",
            "transaction_hex is not a complete serialized Bitcoin transaction.",
        ) from exc

    if tx.to_bytes() != raw_transaction:
        raise TraceRequestError(
            "invalid-transaction",
            "transaction_hex contains trailing or non-canonical transaction data.",
        )
    if request.input_index >= len(tx.inputs):
        raise TraceRequestError(
            "input-index-out-of-range",
            "input_index does not identify an input in the transaction.",
        )
    if len(request.spent_outputs) != len(tx.inputs):
        raise TraceRequestError(
            "spent-output-count",
            "spent_outputs must contain exactly one item for every transaction input.",
        )

    spent_outputs = [
        UTXO(
            outpoint=tx.inputs[index].outpoint,
            amount=descriptor.amount_sats,
            scriptpubkey=bytes.fromhex(descriptor.script_pubkey_hex),
            block_height=0,
        )
        for index, descriptor in enumerate(request.spent_outputs)
    ]
    try:
        result = trace_p2pkh_spend(tx, request.input_index, spent_outputs)
    except ValueError as exc:
        message = str(exc)
        if "not a legacy P2PKH" in message:
            code = "unsupported-script-type"
        elif "P2PKH scriptSig" in message:
            code = "invalid-unlocking-script"
        else:
            code = "invalid-spend-context"
        raise TraceRequestError(code, message) from exc
    except Exception as exc:
        raise TraceRequestError(
            "execution-error",
            "Bitclone could not execute the supplied P2PKH spend context.",
        ) from exc

    return _result_response(result, tx)
