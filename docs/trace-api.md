# P2PKH Trace API

## Endpoint

`POST /api/v1/traces/p2pkh` validates and traces one legacy P2PKH transaction input.

```json
{
  "transaction_hex": "<complete serialized transaction>",
  "input_index": 0,
  "spent_outputs": [
    {
      "amount_sats": 82974043165,
      "script_pubkey_hex": "76a91455ae51684c43435da751ac8d2173b2652eb6410588ac"
    }
  ]
}
```

`spent_outputs` must contain exactly one descriptor for every transaction input, in input order. The selected spent
output must be legacy P2PKH and the selected transaction input must contain a P2PKH scriptSig.

## Success and script failure

Both successful execution and normal Bitcoin Script failure return HTTP 200. The response contains:

- `api_version: "v1"` for the HTTP contract;
- `script_type: "P2PKH"` and the selected input index;
- the unlocking, locking, and combined serialized scripts; and
- the schema-versioned Bitclone trace with ordered steps, stack snapshots, explanations, outcome, and safe diagnostic.

Normal failures use `trace.success: false`. This lets the visualizer teach a failed signature or script without treating
the lesson itself as a failed HTTP request.

## Request errors

Malformed and unsupported requests return HTTP 422:

```json
{
  "error": {
    "code": "unsupported-script-type",
    "message": "Selected spent output is not a legacy P2PKH script"
  }
}
```

Stable codes include `request-validation`, `invalid-transaction`, `input-index-out-of-range`, `spent-output-count`,
`unsupported-script-type`, `invalid-unlocking-script`, `invalid-spend-context`, and `execution-error`.

The public diagnostic intentionally omits Bitclone's internal exception type and never includes a Python traceback.
