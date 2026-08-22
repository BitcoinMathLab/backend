import httpx
import pytest

from bml_backend.app import create_app
from bml_backend.bitcoin_core import (
    SpentOutputContext,
    TransactionContext,
    TransactionOutputContext,
    TransactionSourceError,
)


TXID = "11" * 32
PREVIOUS_TXID = "22" * 32


pytestmark = pytest.mark.anyio


@pytest.fixture
def anyio_backend():
    return "asyncio"


class FakeTransactionSource:
    def __init__(self, result):
        self.result = result
        self.txids = []

    def load_context(self, txid):
        self.txids.append(txid)
        if isinstance(self.result, Exception):
            raise self.result
        return self.result


async def request(application, txid=TXID):
    transport = httpx.ASGITransport(app=application, raise_app_exceptions=False)
    async with httpx.AsyncClient(transport=transport, base_url="http://api") as client:
        return await client.get(f"/api/v1/transactions/{txid}/context")


async def test_returns_versioned_transaction_and_spent_output_context():
    source = FakeTransactionSource(
        TransactionContext(
            txid=TXID,
            wtxid=TXID,
            transaction_hex="01000000000100",
            version=1,
            locktime=0,
            is_segwit=False,
            is_coinbase=False,
            outputs=(
                TransactionOutputContext(
                    vout=0,
                    amount_sats=54_321,
                    script_pubkey_hex="52",
                ),
            ),
            spent_outputs=(
                SpentOutputContext(
                    txid=PREVIOUS_TXID,
                    vout=1,
                    amount_sats=12_345,
                    script_pubkey_hex="76a914" + "33" * 20 + "88ac",
                    output_type="P2PKH",
                    spend_type="P2PKH",
                ),
            ),
        )
    )
    response = await request(create_app(cors_origins=[], transaction_source=source))

    assert response.status_code == 200
    assert response.json() == {
        "api_version": "v1",
        "txid": TXID,
        "wtxid": TXID,
        "transaction_hex": "01000000000100",
        "version": 1,
        "locktime": 0,
        "is_segwit": False,
        "is_coinbase": False,
        "outputs": [
            {
                "vout": 0,
                "amount_sats": 54_321,
                "script_pubkey_hex": "52",
            }
        ],
        "spent_outputs": [
            {
                "txid": PREVIOUS_TXID,
                "vout": 1,
                "amount_sats": 12_345,
                "script_pubkey_hex": "76a914" + "33" * 20 + "88ac",
                "output_type": "P2PKH",
                "spend_type": "P2PKH",
                "is_nested": False,
                "redeem_script_hex": None,
            }
        ],
    }
    assert source.txids == [TXID]
    assert len(response.headers["x-request-id"]) == 32


async def test_reports_unconfigured_core_as_service_unavailable():
    response = await request(create_app(cors_origins=[], transaction_source=None))

    assert response.status_code == 503
    assert response.json()["error"] == {
        "code": "bitcoin-core-not-configured",
        "message": "Bitcoin Core transaction lookup is not configured.",
    }


@pytest.mark.parametrize(
    "error, expected_status",
    [
        (TransactionSourceError("invalid-txid", "safe invalid txid"), 422),
        (TransactionSourceError("bitcoin-core-unavailable", "safe unavailable"), 503),
        (TransactionSourceError("invalid-source-data", "safe source error"), 502),
        (TransactionSourceError("previous-output-missing", "safe source error"), 502),
    ],
)
async def test_maps_source_failures_to_stable_http_errors(error, expected_status):
    response = await request(
        create_app(cors_origins=[], transaction_source=FakeTransactionSource(error))
    )

    assert response.status_code == expected_status
    assert response.json()["error"] == {"code": error.code, "message": error.message}


async def test_openapi_publishes_transaction_context_contract():
    application = create_app(cors_origins=[], transaction_source=None)
    transport = httpx.ASGITransport(app=application)
    async with httpx.AsyncClient(transport=transport, base_url="http://api") as client:
        response = await client.get("/api/v1/openapi.json")

    operation = response.json()["paths"]["/api/v1/transactions/{txid}/context"]["get"]
    assert operation["responses"]["200"]["content"]["application/json"]["schema"]["$ref"].endswith(
        "/TransactionContextResponse"
    )
