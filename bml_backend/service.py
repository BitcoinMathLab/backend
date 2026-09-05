"""Product orchestration around Bitclone's transport-neutral trace engine."""
from __future__ import annotations

from dataclasses import dataclass

from src.script import (
    ECDSASignatureVerificationResult,
    P2MSTraceResult,
    P2PKHTraceResult,
    P2WPKHTraceResult,
    get_legacy_sighash,
    get_legacy_sighash_preimage,
    get_segwit_sighash,
    get_segwit_sighash_preimage,
    trace_p2pkh_spend,
    trace_p2ms_spend,
    trace_p2wpkh_spend,
    verify_ecdsa_sig,
    verify_input_ecdsa_signature,
)
from src.core import serialize_data
from src.tx import Tx, UTXO

from bml_backend.models import (
    ECDSASignatureVerificationRequest,
    ECDSASignatureVerificationResponse,
    ExecutionTraceResponse,
    OpcodeResponse,
    P2MSMetadataResponse,
    P2MSTraceResponse,
    P2PKHTraceRequest,
    P2PKHTraceResponse,
    P2WPKHScriptsResponse,
    P2WPKHTraceResponse,
    P2WPKHTraceSourcesResponse,
    ScriptPairResponse,
    ScriptSourceResponse,
    SignatureVerificationResponse,
    SegwitV0SignatureVerificationResponse,
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
        trace=_trace_response(result.trace),
    )


def _p2ms_result_response(result: P2MSTraceResult, tx: Tx) -> P2MSTraceResponse:
    return P2MSTraceResponse(
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
        multisig=P2MSMetadataResponse(
            required_signatures=result.required_signatures,
            total_public_keys=len(result.public_keys),
            signatures=[signature.hex() for signature in result.signatures],
            public_keys=[public_key.hex() for public_key in result.public_keys],
            has_null_dummy=result.null_dummy == b"",
        ),
        trace=_trace_response(result.trace),
    )


def _trace_steps(trace) -> list[TraceStepResponse]:
    steps = []
    for step in trace.steps:
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

    return steps


def _trace_response(trace) -> ExecutionTraceResponse:
    return ExecutionTraceResponse(
        schema_version=trace.SCHEMA_VERSION,
        script=trace.script.hex(),
        success=bool(trace.success),
        steps=_trace_steps(trace),
        diagnostic=_diagnostic_response(trace.diagnostic),
    )


def _p2wpkh_signature_response(
    result: P2WPKHTraceResult, tx: Tx, amount_sats: int
) -> SegwitV0SignatureVerificationResponse:
    signature_with_type, public_key = result.witness
    sighash_type = signature_with_type[-1]
    serialized_script_code = serialize_data(result.script_code)
    preimage = get_segwit_sighash_preimage(
        tx, result.input_index, amount_sats, serialized_script_code, sighash_type
    )
    digest = get_segwit_sighash(
        tx, result.input_index, amount_sats, serialized_script_code, sighash_type
    )
    return SegwitV0SignatureVerificationResponse(
        algorithm="ECDSA/secp256k1",
        signature_hex=signature_with_type[:-1].hex(),
        public_key_hex=public_key.hex(),
        sighash_type=sighash_type,
        sighash_label=_sighash_label(sighash_type),
        preimage_hex=preimage.hex(),
        digest_hex=digest.hex(),
        valid=verify_ecdsa_sig(signature_with_type[:-1], digest, public_key),
        hash_prevouts_hex=preimage[4:36].hex(),
        hash_sequence_hex=preimage[36:68].hex(),
        hash_outputs_hex=preimage[-40:-8].hex(),
        script_code_hex=serialized_script_code.hex(),
        amount_sats=amount_sats,
    )


def _candidate_signature_response(
    result: ECDSASignatureVerificationResult,
) -> SignatureVerificationResponse | SegwitV0SignatureVerificationResponse:
    common = {
        "algorithm": "ECDSA/secp256k1",
        "signature_hex": result.signature.hex(),
        "public_key_hex": result.public_key.hex(),
        "sighash_type": result.sighash_type,
        "sighash_label": _sighash_label(result.sighash_type),
        "preimage_hex": result.preimage.hex(),
        "digest_hex": result.digest.hex(),
        "valid": result.valid,
    }
    if result.script_type == "P2WPKH":
        if result.script_code is None or result.amount is None:  # pragma: no cover - engine invariant
            raise RuntimeError("P2WPKH signature verification context is incomplete")
        return SegwitV0SignatureVerificationResponse(
            **common,
            hash_prevouts_hex=result.preimage[4:36].hex(),
            hash_sequence_hex=result.preimage[36:68].hex(),
            hash_outputs_hex=result.preimage[-40:-8].hex(),
            script_code_hex=serialize_data(result.script_code).hex(),
            amount_sats=result.amount,
        )
    return SignatureVerificationResponse(**common)


def execute_ecdsa_signature_verification(
    request: ECDSASignatureVerificationRequest,
) -> ECDSASignatureVerificationResponse:
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
        result = verify_input_ecdsa_signature(
            tx,
            request.input_index,
            spent_outputs,
            bytes.fromhex(request.der_signature_hex),
        )
    except ValueError as exc:
        message = str(exc)
        if "strict DER" in message:
            code = "invalid-der-signature"
            message = "der_signature_hex is not a strict DER-encoded ECDSA signature."
        elif "not P2PKH or native P2WPKH" in message:
            code = "unsupported-script-type"
        elif "scriptSig" in message or "witness" in message or "public key" in message:
            code = "invalid-unlocking-data"
        else:
            code = "invalid-spend-context"
        raise TraceRequestError(code, message) from exc
    except Exception as exc:
        raise TraceRequestError(
            "verification-error",
            "Bitclone could not verify the supplied ECDSA signature.",
        ) from exc

    source_txid = tx.txid[::-1].hex()
    previous_source = ScriptSourceResponse(
        transaction_txid=tx.inputs[result.input_index].txid[::-1].hex(),
        index=tx.inputs[result.input_index].vout,
    )
    if result.script_type == "P2WPKH":
        if result.script_code is None:  # pragma: no cover - engine invariant
            raise RuntimeError("P2WPKH signature verification scriptCode is missing")
        scripts = P2WPKHScriptsResponse(
            witness=[item.hex() for item in result.witness],
            locking=result.locking_script.hex(),
            script_code=result.script_code.hex(),
        )
        sources = P2WPKHTraceSourcesResponse(
            witness=ScriptSourceResponse(transaction_txid=source_txid, index=result.input_index),
            script_pubkey=previous_source,
        )
    else:
        scripts = ScriptPairResponse(
            unlocking=result.unlocking_script.hex(),
            locking=result.locking_script.hex(),
            combined=(result.unlocking_script + result.locking_script).hex(),
        )
        sources = TraceSourcesResponse(
            script_sig=ScriptSourceResponse(
                transaction_txid=source_txid, index=result.input_index
            ),
            script_pubkey=previous_source,
        )
    return ECDSASignatureVerificationResponse(
        script_type=result.script_type,
        input_index=result.input_index,
        scripts=scripts,
        sources=sources,
        signature=_candidate_signature_response(result),
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


def execute_p2wpkh_trace(request: P2PKHTraceRequest) -> P2WPKHTraceResponse:
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
        result = trace_p2wpkh_spend(tx, request.input_index, spent_outputs)
    except ValueError as exc:
        message = str(exc)
        if "not a native P2WPKH" in message:
            code = "unsupported-script-type"
        elif "witness" in message or "scriptSig" in message:
            code = "invalid-unlocking-data"
        else:
            code = "invalid-spend-context"
        raise TraceRequestError(code, message) from exc
    except Exception as exc:
        raise TraceRequestError(
            "execution-error",
            "Bitclone could not execute the supplied P2WPKH spend context.",
        ) from exc

    return P2WPKHTraceResponse(
        input_index=result.input_index,
        scripts=P2WPKHScriptsResponse(
            witness=[item.hex() for item in result.witness],
            locking=result.locking_script.hex(),
            script_code=result.script_code.hex(),
        ),
        sources=P2WPKHTraceSourcesResponse(
            witness=ScriptSourceResponse(
                transaction_txid=tx.txid[::-1].hex(), index=result.input_index
            ),
            script_pubkey=ScriptSourceResponse(
                transaction_txid=tx.inputs[result.input_index].txid[::-1].hex(),
                index=tx.inputs[result.input_index].vout,
            ),
        ),
        signature=_p2wpkh_signature_response(
            result, tx, spent_outputs[result.input_index].amount
        ),
        trace=_trace_response(result.trace),
    )


def execute_p2ms_trace(request: P2PKHTraceRequest) -> P2MSTraceResponse:
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
        result = trace_p2ms_spend(tx, request.input_index, spent_outputs)
    except ValueError as exc:
        message = str(exc)
        if "not a legacy bare P2MS" in message:
            code = "unsupported-script-type"
        elif "P2MS scriptSig" in message:
            code = "invalid-unlocking-script"
        else:
            code = "invalid-spend-context"
        raise TraceRequestError(code, message) from exc
    except Exception as exc:
        raise TraceRequestError(
            "execution-error",
            "Bitclone could not execute the supplied P2MS spend context.",
        ) from exc

    return _p2ms_result_response(result, tx)
