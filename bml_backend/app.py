"""FastAPI application for Bitcoin Math Lab."""
from __future__ import annotations

import json
import logging
import os
import re
from collections.abc import Awaitable, Callable, Sequence
from time import perf_counter
from urllib.parse import urlsplit
from uuid import uuid4

from fastapi import FastAPI, Request, Response
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from bml_backend import __version__
from bml_backend.bitcoin_core import TransactionContextSource, TransactionSourceError
from bml_backend.config import transaction_source_from_environment
from bml_backend.models import (
    ErrorResponse,
    P2PKHTraceRequest,
    P2PKHTraceResponse,
    PreviousOutputResponse,
    TransactionContextResponse,
    TransactionOutputResponse,
)
from bml_backend.service import TraceRequestError, execute_p2pkh_trace


request_logger = logging.getLogger("uvicorn.error.bml_backend.requests")
request_logger.setLevel(logging.INFO)
_ENVIRONMENT_SOURCE = object()


async def trace_request_error_handler(_request: Request, exc: TraceRequestError) -> JSONResponse:
    return JSONResponse(
        status_code=422,
        content={"error": {"code": exc.code, "message": exc.message}},
    )


async def request_validation_error_handler(_request: Request, _exc: RequestValidationError) -> JSONResponse:
    return JSONResponse(
        status_code=422,
        content={
            "error": {
                "code": "request-validation",
                "message": "The request does not match the v1 API contract.",
            }
        },
    )


async def transaction_source_error_handler(
    _request: Request, exc: TransactionSourceError
) -> JSONResponse:
    status_code = {
        "invalid-txid": 422,
        "bitcoin-core-not-configured": 503,
        "bitcoin-core-unavailable": 503,
        "invalid-source-data": 502,
        "previous-output-missing": 502,
    }.get(exc.code, 502)
    return JSONResponse(
        status_code=status_code,
        content={"error": {"code": exc.code, "message": exc.message}},
    )


def parse_release_identifier(raw_release: str) -> str | None:
    """Validate the public deployment identity exposed by the health endpoint."""
    release = raw_release.strip()
    if not release:
        return None
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._/-]{0,127}", release):
        raise ValueError("BML_RELEASE must be a safe identifier of at most 128 characters")
    return release


async def p2pkh_trace(request: P2PKHTraceRequest) -> P2PKHTraceResponse:
    return execute_p2pkh_trace(request)


async def observe_request(
    request: Request, call_next: Callable[[Request], Awaitable[Response]]
) -> Response:
    """Attach a correlation ID and emit a body-free structured request record."""
    request_id = uuid4().hex
    started = perf_counter()
    try:
        response = await call_next(request)
    except Exception as exc:
        duration_ms = round((perf_counter() - started) * 1_000, 2)
        request_logger.error(
            json.dumps(
                {
                    "event": "request_error",
                    "request_id": request_id,
                    "method": request.method,
                    "path": request.url.path,
                    "status_code": 500,
                    "duration_ms": duration_ms,
                    "exception_type": type(exc).__name__,
                },
                separators=(",", ":"),
            )
        )
        response = JSONResponse(
            status_code=500,
            content={
                "error": {
                    "code": "internal-error",
                    "message": "The request could not be completed.",
                },
                "request_id": request_id,
            },
        )
    else:
        duration_ms = round((perf_counter() - started) * 1_000, 2)
        request_logger.info(
            json.dumps(
                {
                    "event": "request_complete",
                    "request_id": request_id,
                    "method": request.method,
                    "path": request.url.path,
                    "status_code": response.status_code,
                    "duration_ms": duration_ms,
                },
                separators=(",", ":"),
            )
        )

    response.headers["X-Request-ID"] = request_id
    return response


def parse_cors_origins(raw_origins: str) -> tuple[str, ...]:
    """Parse and validate the comma-separated browser origins used by CORS."""
    origins: list[str] = []
    for candidate in raw_origins.split(","):
        candidate = candidate.strip().rstrip("/")
        if not candidate:
            continue
        parsed = urlsplit(candidate)
        if (
            parsed.scheme not in {"http", "https"}
            or not parsed.netloc
            or parsed.path
            or parsed.query
            or parsed.fragment
        ):
            raise ValueError(f"BML_CORS_ORIGINS contains an invalid origin: {candidate!r}")
        if candidate not in origins:
            origins.append(candidate)
    return tuple(origins)


def create_app(
    cors_origins: Sequence[str] | None = None,
    release: str | None = None,
    transaction_source: TransactionContextSource | None | object = _ENVIRONMENT_SOURCE,
) -> FastAPI:
    application = FastAPI(
        title="Bitcoin Math Lab API",
        version=__version__,
        description="Educational Bitcoin execution and analysis APIs.",
        openapi_url="/api/v1/openapi.json",
    )

    configured_origins = (
        tuple(cors_origins)
        if cors_origins is not None
        else parse_cors_origins(os.getenv("BML_CORS_ORIGINS", ""))
    )
    configured_release = parse_release_identifier(
        release if release is not None else os.getenv("BML_RELEASE", "")
    )
    configured_transaction_source = (
        transaction_source_from_environment()
        if transaction_source is _ENVIRONMENT_SOURCE
        else transaction_source
    )

    async def configured_health() -> dict[str, str]:
        response = {"status": "ok", "version": __version__}
        if configured_release is not None:
            response["release"] = configured_release
        return response

    def configured_transaction_context(txid: str) -> TransactionContextResponse:
        if configured_transaction_source is None:
            raise TransactionSourceError(
                "bitcoin-core-not-configured",
                "Bitcoin Core transaction lookup is not configured.",
            )
        context = configured_transaction_source.load_context(txid)
        return TransactionContextResponse(
            txid=context.txid,
            transaction_hex=context.transaction_hex,
            is_coinbase=context.is_coinbase,
            outputs=[
                TransactionOutputResponse(
                    vout=output.vout,
                    amount_sats=output.amount_sats,
                    script_pubkey_hex=output.script_pubkey_hex,
                )
                for output in context.outputs
            ],
            spent_outputs=[
                PreviousOutputResponse(
                    txid=output.txid,
                    vout=output.vout,
                    amount_sats=output.amount_sats,
                    script_pubkey_hex=output.script_pubkey_hex,
                    output_type=output.output_type,
                    spend_type=output.spend_type,
                    is_nested=output.is_nested,
                    redeem_script_hex=output.redeem_script_hex,
                )
                for output in context.spent_outputs
            ],
        )

    if configured_origins:
        application.add_middleware(
            CORSMiddleware,
            allow_origins=list(configured_origins),
            allow_methods=["GET", "POST", "OPTIONS"],
            allow_headers=["Content-Type"],
            expose_headers=["X-Request-ID"],
        )

    application.middleware("http")(observe_request)

    application.add_exception_handler(TraceRequestError, trace_request_error_handler)
    application.add_exception_handler(TransactionSourceError, transaction_source_error_handler)
    application.add_exception_handler(RequestValidationError, request_validation_error_handler)
    application.add_api_route(
        "/api/v1/health", configured_health, methods=["GET"], tags=["system"]
    )
    application.add_api_route(
        "/api/v1/traces/p2pkh",
        p2pkh_trace,
        methods=["POST"],
        response_model=P2PKHTraceResponse,
        responses={422: {"model": ErrorResponse}, 500: {"model": ErrorResponse}},
        tags=["traces"],
    )
    application.add_api_route(
        "/api/v1/transactions/{txid}/context",
        configured_transaction_context,
        methods=["GET"],
        response_model=TransactionContextResponse,
        responses={
            422: {"model": ErrorResponse},
            502: {"model": ErrorResponse},
            503: {"model": ErrorResponse},
        },
        tags=["transactions"],
    )
    return application


app = create_app()
