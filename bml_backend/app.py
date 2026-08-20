"""FastAPI application for Bitcoin Math Lab."""
from __future__ import annotations

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from bml_backend import __version__
from bml_backend.models import ErrorResponse, P2PKHTraceRequest, P2PKHTraceResponse
from bml_backend.service import TraceRequestError, execute_p2pkh_trace


app = FastAPI(
    title="Bitcoin Math Lab API",
    version=__version__,
    description="Educational Bitcoin execution and analysis APIs.",
    openapi_url="/api/v1/openapi.json",
)


@app.exception_handler(TraceRequestError)
async def trace_request_error_handler(_request: Request, exc: TraceRequestError) -> JSONResponse:
    return JSONResponse(
        status_code=422,
        content={"error": {"code": exc.code, "message": exc.message}},
    )


@app.exception_handler(RequestValidationError)
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


@app.get("/api/v1/health", tags=["system"])
async def health() -> dict[str, str]:
    return {"status": "ok", "version": __version__}


@app.post(
    "/api/v1/traces/p2pkh",
    response_model=P2PKHTraceResponse,
    responses={422: {"model": ErrorResponse}},
    tags=["traces"],
)
async def p2pkh_trace(request: P2PKHTraceRequest) -> P2PKHTraceResponse:
    return execute_p2pkh_trace(request)
