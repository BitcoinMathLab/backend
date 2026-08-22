# Transaction examples API

`GET /api/v1/transactions/examples` returns the stable, versioned catalog used to teach real transaction concepts in
the explorer. It does not require Bitcoin Core, perform RPC calls, or expose infrastructure details.

Each example includes:

- a stable slug, title, and short learner-facing description;
- a confirmed mainnet transaction ID;
- the expected explorer input and output counts;
- expected input spend classifications; and
- concepts suitable for labels and guided explanations.

The initial catalog covers the genesis coinbase, an early payment/change transaction, legacy P2PKH, native P2WPKH,
and native P2WSH. Its expected shapes and classifications were verified against the synchronized development node.

## QA

1. Request `/api/v1/transactions/examples` while Bitcoin Core is stopped; expect HTTP 200 and five examples.
2. Select each txid and request its transaction context with Core running.
3. Confirm the returned input/output counts and spend classifications match the catalog.
4. Confirm no duplicate slugs or txids appear.
