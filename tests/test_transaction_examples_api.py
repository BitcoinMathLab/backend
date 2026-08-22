import httpx
import pytest

from bml_backend.app import create_app
from bml_backend.transaction_examples import TRANSACTION_EXAMPLES


pytestmark = pytest.mark.anyio


@pytest.fixture
def anyio_backend():
    return "asyncio"


async def test_returns_versioned_examples_without_requiring_bitcoin_core():
    application = create_app(cors_origins=[], transaction_source=None)
    transport = httpx.ASGITransport(app=application)
    async with httpx.AsyncClient(transport=transport, base_url="http://api") as client:
        response = await client.get("/api/v1/transactions/examples")

    assert response.status_code == 200
    body = response.json()
    assert body["api_version"] == "v1"
    assert [example["slug"] for example in body["examples"]] == [
        "genesis-coinbase",
        "early-payment-and-change",
        "legacy-p2pkh",
        "native-segwit-p2wpkh",
        "native-segwit-p2wsh",
    ]
    assert body["examples"][0] == {
        "slug": "genesis-coinbase",
        "title": "Genesis coinbase",
        "description": "Inspect Bitcoin's block-zero coinbase and the output it created.",
        "txid": "4a5e1e4baab89f3a32518a88c31bc87f618f76673e2cc77ab2127b7afdeda33b",
        "input_count": 0,
        "output_count": 1,
        "expected_spend_types": [],
        "concepts": ["coinbase", "block zero", "created output"],
    }
    assert body["examples"][1]["input_count"] == 1
    assert body["examples"][1]["output_count"] == 2
    assert body["examples"][1]["expected_spend_types"] == ["P2PKH"]


def test_catalog_identifiers_and_transaction_ids_are_unique():
    assert len({example.slug for example in TRANSACTION_EXAMPLES}) == len(TRANSACTION_EXAMPLES)
    assert len({example.txid for example in TRANSACTION_EXAMPLES}) == len(TRANSACTION_EXAMPLES)


async def test_openapi_publishes_transaction_examples_contract():
    application = create_app(cors_origins=[], transaction_source=None)
    transport = httpx.ASGITransport(app=application)
    async with httpx.AsyncClient(transport=transport, base_url="http://api") as client:
        response = await client.get("/api/v1/openapi.json")

    operation = response.json()["paths"]["/api/v1/transactions/examples"]["get"]
    schema = operation["responses"]["200"]["content"]["application/json"]["schema"]
    assert schema["$ref"].endswith("/TransactionExamplesResponse")
