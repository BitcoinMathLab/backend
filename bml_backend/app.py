"""FastAPI application for Bitcoin Math Lab."""
from __future__ import annotations

import os
from collections.abc import Sequence
from urllib.parse import urlsplit

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from bml_backend import __version__
from bml_backend.models import ErrorResponse, P2PKHTraceRequest, P2PKHTraceResponse
from bml_backend.service import TraceRequestError, execute_p2pkh_trace


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
                "message": "The request body does not match the v1 trace contract.",
            }
        },
    )


async def health() -> dict[str, str]:
    return {"status": "ok", "version": __version__}


async def p2pkh_trace(request: P2PKHTraceRequest) -> P2PKHTraceResponse:
    return execute_p2pkh_trace(request)


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


def create_app(cors_origins: Sequence[str] | None = None) -> FastAPI:
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
    if configured_origins:
        application.add_middleware(
            CORSMiddleware,
            allow_origins=list(configured_origins),
            allow_methods=["GET", "POST", "OPTIONS"],
            allow_headers=["Content-Type"],
        )

    application.add_exception_handler(TraceRequestError, trace_request_error_handler)
    application.add_exception_handler(RequestValidationError, request_validation_error_handler)
    application.add_api_route("/api/v1/health", health, methods=["GET"], tags=["system"])
    application.add_api_route(
        "/api/v1/traces/p2pkh",
        p2pkh_trace,
        methods=["POST"],
        response_model=P2PKHTraceResponse,
        responses={422: {"model": ErrorResponse}},
        tags=["traces"],
    )
    return application


app = create_app()
