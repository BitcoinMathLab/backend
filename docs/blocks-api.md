# Block lookup API

`GET /api/v1/blocks/{block_hash}?offset=0&limit=25`

`GET /api/v1/blocks/height/{height}?offset=0&limit=25`

Uses the same `BML_CORE_RPC_*` configuration as transaction context lookup. Hashes are
64 hex characters (case insensitive); heights and offsets are nonnegative integers.
The default page size is 25; the maximum is 100. These synchronous routes run in
FastAPI's worker pool so Core I/O does not block the application event loop.

Responses include `block_hash`, `height`, `confirmations`, `version`, `merkle_root`,
`timestamp`, `median_time`, `bits`, `nonce`, `previous_block_hash`, `next_block_hash`,
`size_bytes`, `weight_units`, `transaction_count`, `transaction_ids`, `offset`,
`limit`, and `next_offset`. Hashes use explorer display byte order; timestamps are
Unix seconds. Missing adjacent hashes and the final `next_offset` are null.
Offsets beyond the transaction count return an empty page.

The adapter uses [Core getblock verbosity 1](https://bitcoincore.org/en/doc/30.0.0/rpc/blockchain/getblock/),
which returns metadata and transaction IDs. Pagination bounds the public response;
Core still returns its complete ID list per request. Transaction details and previous
outputs are not fetched. Follow subsequent pages by returned block hash, rather than
height, to keep the selected block stable across a chain reorganization. Confirmations
and adjacent-block metadata are refreshed each request; confirmations may be -1 for a
block outside the active chain.

Historical blocks must be retained by the node (an archival node is required for
arbitrary historical lookup). Block lookup does not require a transaction index;
existing arbitrary historical transaction lookup still does.

Errors use the existing `{ "error": { "code": "...", "message": "..." } }` envelope:

- 422: invalid hash, height, or pagination.
- 502 `invalid-source-data`: malformed or inconsistent Core response.
- 503 `bitcoin-core-not-configured`: no Core configuration.
- 503 `bitcoin-core-unavailable`: Core lookup failed, including unknown/pruned blocks.
  The current Bitclone RPC exception does not preserve structured error codes, so this
  slice does not claim to distinguish not-found from unavailable. RPC details are hidden.

## Review

Start the backend using the Core configuration in the README, then open `/docs` and
try `/api/v1/blocks/height/0`. Expect one transaction and no previous-block link.
Load a larger block by height, then use its returned hash with `limit=100` and the
returned `next_offset`. Expect ordered pages without gaps and a final null offset.
Try `limit=101` (422), then stop/disconnect Core and retry (503).

This slice adds the API only. Display loading and Explorer navigation remain separate
review steps; there are no changed browser layouts to inspect.


Block details also include `target_hex` (64 lowercase hex digits, big-endian,
expanded from header bits) and nullable `money`:

- `subsidy_sats`: network subsidy, excluding fees.
- `fees_sats`: total fees in the whole block.
- `transaction_output_sats`: sum of non-coinbase transaction outputs, including
  change and self-transfers; this is not economic payment volume.

Amounts are decimal strings to preserve integer precision in JavaScript. All
pages report the same whole-block totals. These come from Bitcoin Core
[`getblockstats`](https://bitcoincore.org/en/doc/30.0.0/rpc/blockchain/getblockstats/).
If historical statistics are unavailable or invalid, `money` is null while the
block metadata and transaction IDs remain available. No amounts are inferred.
