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
