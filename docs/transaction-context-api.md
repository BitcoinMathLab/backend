# Transaction context API

`GET /api/v1/transactions/{txid}/context` loads a raw transaction from the configured Bitcoin Core node and returns the
ordered previous-output context required to analyze its inputs.

## Response

```json
{
  "api_version": "v1",
  "txid": "<64 lowercase hex characters>",
  "transaction_hex": "<canonical serialized transaction>",
  "is_coinbase": false,
  "spent_outputs": [
    {
      "txid": "<previous transaction id>",
      "vout": 0,
      "amount_sats": 1000,
      "script_pubkey_hex": "<locking script>"
    }
  ]
}
```

Previous outputs appear in the same order as the transaction inputs. Repeated inputs from one previous transaction use
one Core lookup. Coinbase transactions return `is_coinbase: true` and an empty `spent_outputs` array.

Bitcoin Core intentionally excludes the genesis-block coinbase from `getrawtransaction`. For that exact txid, the
adapter retrieves and verifies block zero, extracts its sole coinbase transaction, and returns the same normal coinbase
context shape. No other failed transaction lookup uses this fallback.

## Stable errors

| HTTP | Code | Meaning |
|---:|---|---|
| 422 | `invalid-txid` | The path does not contain a 32-byte hexadecimal transaction ID |
| 502 | `invalid-source-data` | Core returned malformed or mismatched transaction bytes |
| 502 | `previous-output-missing` | A referenced output is absent from its previous transaction |
| 503 | `bitcoin-core-not-configured` | No Core integration is configured for this backend process |
| 503 | `bitcoin-core-unavailable` | Core could not return the target or a previous transaction |

Core connection details and credentials are never included in these responses.

## QA validation

Automated validation uses a fake Core boundary and covers ordered outputs, duplicate lookup caching, coinbase context,
invalid txids, unavailable Core, malformed source bytes, missing outputs, API response shape, stable HTTP mappings, and
OpenAPI publication.

Manual validation requires a synchronized, unpruned Bitcoin Core node with `txindex=1`:

1. Start Bitclone's SSH/RPC tunnel and confirm `getindexinfo txindex` reports `synced: true`.
2. Start the backend with `BML_CORE_RPC_URL` and `BML_CORE_RPC_COOKIE` as shown in the README.
3. Request
   `/api/v1/transactions/40e331b67c0fe7750bb3b1943b378bf702dce86124dc12fa5980f975db7ec930/context`.
4. Expect HTTP 200, the same txid, one spent output, and `amount_sats: 82974043165`.
5. Request a malformed txid and expect a safe 422 response.
6. Stop the tunnel, retry the known txid, and expect a safe 503 response with an `X-Request-ID` header.
7. Request `4a5e1e4baab89f3a32518a88c31bc87f618f76673e2cc77ab2127b7afdeda33b`. Expect HTTP 200,
   `is_coinbase: true`, and no previous outputs.

The live ordinary-transaction and genesis-coinbase success cases, tunnel operation, cookie authentication, and the safe
unavailable response have passed manual QA against the development Core node.
