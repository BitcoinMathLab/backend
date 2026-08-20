import json
import logging

import httpx
import pytest

from bml_backend.app import create_app, parse_cors_origins


pytestmark = pytest.mark.anyio


@pytest.fixture
def anyio_backend():
    return "asyncio"


def test_cors_origins_are_normalized_and_deduplicated():
    assert parse_cors_origins(
        " https://bitcoinmathlab.com/, https://preview.example.com,https://bitcoinmathlab.com "
    ) == ("https://bitcoinmathlab.com", "https://preview.example.com")


@pytest.mark.parametrize(
    "origin",
    ["*", "bitcoinmathlab.com", "ftp://bitcoinmathlab.com", "https://bitcoinmathlab.com/path"],
)
def test_invalid_cors_origin_fails_at_startup(origin):
    with pytest.raises(ValueError, match="invalid origin"):
        parse_cors_origins(origin)


async def test_configured_frontend_origin_can_call_api():
    application = create_app(cors_origins=["https://bitcoinmathlab.com"])
    transport = httpx.ASGITransport(app=application)
    async with httpx.AsyncClient(transport=transport, base_url="http://api") as client:
        response = await client.get(
            "/api/v1/health",
            headers={"Origin": "https://bitcoinmathlab.com"},
        )

    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == "https://bitcoinmathlab.com"
    assert response.headers["access-control-expose-headers"] == "X-Request-ID"


async def test_unconfigured_origin_is_not_granted_browser_access():
    application = create_app(cors_origins=["https://bitcoinmathlab.com"])
    transport = httpx.ASGITransport(app=application)
    async with httpx.AsyncClient(transport=transport, base_url="http://api") as client:
        response = await client.options(
            "/api/v1/traces/p2pkh",
            headers={
                "Origin": "https://untrusted.example",
                "Access-Control-Request-Method": "POST",
                "Access-Control-Request-Headers": "content-type",
            },
        )

    assert response.status_code == 400
    assert "access-control-allow-origin" not in response.headers


async def test_request_id_correlates_response_and_privacy_safe_log(caplog):
    application = create_app(cors_origins=[])
    transport = httpx.ASGITransport(app=application)
    with caplog.at_level(logging.INFO, logger="uvicorn.error.bml_backend.requests"):
        async with httpx.AsyncClient(transport=transport, base_url="http://api") as client:
            response = await client.get("/api/v1/health?token=must-not-be-logged")

    request_id = response.headers["x-request-id"]
    assert len(request_id) == 32
    record = json.loads(caplog.records[-1].message)
    assert record == {
        "event": "request_complete",
        "request_id": request_id,
        "method": "GET",
        "path": "/api/v1/health",
        "status_code": 200,
        "duration_ms": record["duration_ms"],
    }
    assert "token" not in caplog.records[-1].message


async def test_unhandled_error_is_safe_and_correlatable(caplog):
    application = create_app(cors_origins=[])

    async def fail():
        raise RuntimeError("private internal detail")

    application.add_api_route("/test/failure", fail, methods=["GET"])
    transport = httpx.ASGITransport(app=application, raise_app_exceptions=False)
    with caplog.at_level(logging.ERROR, logger="uvicorn.error.bml_backend.requests"):
        async with httpx.AsyncClient(transport=transport, base_url="http://api") as client:
            response = await client.get("/test/failure")

    assert response.status_code == 500
    assert response.json() == {
        "error": {"code": "internal-error", "message": "The request could not be completed."},
        "request_id": response.headers["x-request-id"],
    }
    assert "private internal detail" not in response.text
    assert "private internal detail" not in caplog.records[-1].message
    assert json.loads(caplog.records[-1].message)["request_id"] == response.headers["x-request-id"]
