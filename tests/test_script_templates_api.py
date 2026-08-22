import httpx
import pytest
from src.script import P2TR_Key

from bml_backend.app import create_app


pytestmark = pytest.mark.anyio


@pytest.fixture
def anyio_backend():
    return "asyncio"


async def post(payload):
    application = create_app(cors_origins=[], transaction_source=None)
    transport = httpx.ASGITransport(app=application, raise_app_exceptions=False)
    async with httpx.AsyncClient(transport=transport, base_url="http://api") as client:
        return await client.post("/api/v1/scripts/templates", json=payload)


@pytest.mark.parametrize(
    ("template", "program_hex", "script_type", "script_prefix", "address_prefix"),
    [
        ("P2SH", "11" * 20, "P2SH", "a914", "3"),
        ("P2WPKH", "22" * 20, "P2WPKH", "0014", "bc1q"),
        ("P2WSH", "33" * 32, "P2WSH", "0020", "bc1q"),
    ],
)
async def test_builds_versioned_standard_script_templates(
    template, program_hex, script_type, script_prefix, address_prefix
):
    response = await post({"template": template, "program_hex": program_hex.upper()})

    assert response.status_code == 200
    assert response.json() == {
        "api_version": "v1",
        "template": template,
        "script_type": script_type,
        "program_hex": program_hex,
        "script_pubkey_hex": script_prefix + program_hex + ("87" if template == "P2SH" else ""),
        "address": response.json()["address"],
    }
    assert response.json()["address"].startswith(address_prefix)


@pytest.mark.parametrize("template", ["P2TR-KEY-PATH", "P2TR-SCRIPT-PATH"])
async def test_builds_both_taproot_template_intents(template):
    internal_key = bytes.fromhex(
        "924c163b385af7093440184af6fd6244936d1288cbb41cc3812286d3f83a3329"
    )
    output_key_hex = P2TR_Key(internal_key).script[2:].hex()

    response = await post({"template": template, "program_hex": output_key_hex})

    assert response.status_code == 200
    assert response.json()["script_type"] == "P2TR"
    assert response.json()["script_pubkey_hex"] == "5120" + output_key_hex
    assert response.json()["address"].startswith("bc1p")


async def test_returns_a_stable_error_for_the_wrong_program_length():
    response = await post({"template": "P2WPKH", "program_hex": "11" * 19})

    assert response.status_code == 422
    assert response.json()["error"] == {
        "code": "invalid-script-template",
        "message": "P2WPKH requires a 20-byte program",
    }
    assert len(response.headers["x-request-id"]) == 32


async def test_openapi_publishes_standard_script_template_contract():
    application = create_app(cors_origins=[], transaction_source=None)
    transport = httpx.ASGITransport(app=application)
    async with httpx.AsyncClient(transport=transport, base_url="http://api") as client:
        response = await client.get("/api/v1/openapi.json")

    operation = response.json()["paths"]["/api/v1/scripts/templates"]["post"]
    schema = operation["responses"]["200"]["content"]["application/json"]["schema"]
    assert schema["$ref"].endswith("/StandardScriptTemplateResponse")
