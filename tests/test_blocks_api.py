from unittest.mock import Mock

import pytest
import httpx
from src.database.bitcoin_core_rpc import BitcoinCoreRPCError

from bml_backend.app import create_app
from bml_backend.blocks import BitcoinCoreBlockSource

pytestmark = pytest.mark.anyio


@pytest.fixture
def anyio_backend():
    return 'asyncio'


def api_client(app):
    return httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://api')


BLOCK_HASH = 'ab' * 32
TXIDS = [f'{i:064x}' for i in range(205)]


def block_data():
    return dict(hash=BLOCK_HASH, height=100, confirmations=3, version=1,
                merkleroot='cd' * 32, time=1231006505, mediantime=1231006505,
                bits='1d00ffff', nonce=2083236893, size=285, weight=1140,
                nTx=len(TXIDS), tx=TXIDS, previousblockhash='ef' * 32)


def stats_data(**patch):
    return dict(blockhash=BLOCK_HASH, height=100, subsidy=5000000000,
                totalfee=12345, total_out=9007199254740993) | patch


def setup_client(data=None):
    rpc = Mock()
    rpc.call.side_effect = lambda method, *args: (stats_data() if method == "getblockstats" else (block_data() if data is None else data))
    source = BitcoinCoreBlockSource(rpc)
    return rpc, api_client(create_app(transaction_source=None, block_source=source))


async def test_hash_lookup_normalizes_and_returns_metadata_without_transaction_fetches():
    rpc, client = setup_client()
    response = await client.get(f'/api/v1/blocks/{BLOCK_HASH.upper()}')
    assert response.status_code == 200
    data = response.json()
    assert data['block_hash'] == BLOCK_HASH
    assert data['transaction_ids'] == TXIDS[:25]
    assert data['transaction_count'] == 205
    assert data['next_offset'] == 25
    assert data['previous_block_hash'] == 'ef' * 32
    assert data['next_block_hash'] is None
    assert data['weight_units'] == 1140
    assert data['target_hex'] == '00000000ffff0000000000000000000000000000000000000000000000000000'
    assert data['money'] == dict(subsidy_sats='5000000000', fees_sats='12345',
                                 transaction_output_sats='9007199254740993')
    assert rpc.call.call_args_list[0].args == ('getblock', BLOCK_HASH, 1)
    assert rpc.call.call_count == 2


async def test_height_lookup_and_genesis_missing_links():
    block = block_data()
    block.update(height=0, nTx=1, tx=TXIDS[:1])
    del block['previousblockhash']
    rpc, client = setup_client()
    rpc.call.side_effect = [BLOCK_HASH, block, stats_data(height=0)]
    response = await client.get('/api/v1/blocks/height/0')
    assert response.status_code == 200
    assert response.json()['previous_block_hash'] is None
    assert response.json()['next_offset'] is None
    assert rpc.call.call_args_list[0].args == ('getblockhash', 0)


async def test_pagination_covers_large_block_without_gaps_and_handles_past_end():
    _, client = setup_client()
    found = []
    offset = 0
    while offset is not None:
        response = await client.get(f'/api/v1/blocks/{BLOCK_HASH}?offset={offset}&limit=100')
        assert response.status_code == 200
        data = response.json()
        found.extend(data['transaction_ids'])
        offset = data['next_offset']
    assert found == TXIDS
    data = (await client.get(f'/api/v1/blocks/{BLOCK_HASH}?offset=999')).json()
    assert data['transaction_ids'] == []
    assert data['next_offset'] is None


@pytest.mark.parametrize('path', [
    'bad', 'gg' * 32, 'height/-1', 'height/nope',
    BLOCK_HASH + '?offset=-1', BLOCK_HASH + '?limit=0',
    BLOCK_HASH + '?limit=101', BLOCK_HASH + '?offset=1.5',
])
async def test_invalid_requests_do_not_call_core(path):
    rpc, client = setup_client()
    assert (await client.get('/api/v1/blocks/' + path)).status_code == 422
    rpc.call.assert_not_called()


@pytest.mark.parametrize('patch', [
    {'hash': '00' * 32}, {'nTx': 1}, {'weight': '1140'},
    {'tx': ['not-a-txid']}, {'bits': 'invalid'}, {'height': -1},
])
async def test_invalid_upstream_data_is_502(patch):
    data = block_data()
    data.update(patch)
    _, client = setup_client(data)
    response = await client.get(f'/api/v1/blocks/{BLOCK_HASH}')
    assert response.status_code == 502
    assert response.json()['error']['code'] == 'invalid-source-data'


async def test_height_mismatch_is_rejected():
    rpc, client = setup_client()
    rpc.call.side_effect = [BLOCK_HASH, block_data()]
    assert (await client.get('/api/v1/blocks/height/99')).status_code == 502


async def test_unavailable_core_does_not_expose_rpc_details():
    rpc, client = setup_client()
    rpc.call.side_effect = BitcoinCoreRPCError('private upstream detail')
    response = await client.get(f'/api/v1/blocks/{BLOCK_HASH}')
    assert response.status_code == 503
    assert 'private' not in response.text


async def test_unconfigured_core_and_openapi_contract():
    client = api_client(create_app(transaction_source=None, block_source=None))
    response = await client.get(f'/api/v1/blocks/{BLOCK_HASH}')
    assert response.status_code == 503
    assert response.json()['error']['code'] == 'bitcoin-core-not-configured'
    assert '/api/v1/blocks/{block_hash}' in (await client.get('/api/v1/openapi.json')).json()['paths']


@pytest.mark.parametrize('stats', [stats_data(blockhash='00' * 32), stats_data(height=99),
                                  stats_data(totalfee=-1), stats_data(total_out=1.5),
                                  BitcoinCoreRPCError('private stats failure')])
async def test_unavailable_or_invalid_stats_preserve_block_without_fake_amounts(stats):
    rpc, client = setup_client()
    rpc.call.side_effect = [block_data(), stats]
    response = await client.get(f'/api/v1/blocks/{BLOCK_HASH}')
    assert response.status_code == 200
    assert response.json()['money'] is None
    assert 'private' not in response.text
