# P2PKH, P2WPKH, and P2MS Trace API

## Endpoint

`POST /api/v1/traces/p2pkh` validates and traces one legacy P2PKH transaction input.

`POST /api/v1/traces/p2wpkh` accepts the same request shape and validates a native SegWit-v0 P2WPKH input. Its
`scriptSig` must be empty and its witness must contain exactly the DER signature/hash-type item and compressed public
key. The trace begins with those real witness items on the stack and executes the P2PKH `scriptCode` derived from the
20-byte witness program.

`POST /api/v1/traces/p2ms` accepts the same request shape and validates one legacy bare P2MS input. The spent output
must be a direct m-of-n multisig scriptPubKey rather than a P2SH wrapper. The scriptSig must contain the historical
empty CHECKMULTISIG dummy followed by the serialized signatures.

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
output must match the endpoint's script family and the selected transaction input must contain that family's expected
scriptSig or witness structure.

## Success and script failure

Both successful execution and normal Bitcoin Script failure return HTTP 200. The response contains:

- `api_version: "v1"` for the HTTP contract;
- `script_type: "P2PKH"` and the selected input index;
- the unlocking, locking, and combined serialized scripts;
- the spending-input and previous-output transaction provenance;
- the DER signature, public key, sighash type, exact legacy preimage, double-SHA-256 digest, and ECDSA result; and
- the schema-versioned Bitclone trace with ordered steps, stack snapshots, explanations, outcome, and safe diagnostic.

The preimage is the exact byte sequence hashed by the legacy signature algorithm: all input scripts are cleared, the
selected input receives the spent output's `scriptPubKey`, and the four-byte sighash type is appended. It contains only
public transaction data and is suitable for an educational byte walkthrough.

For P2WPKH, the response additionally exposes the witness items, witness program, derived serialized `scriptCode`,
spent amount, `hashPrevouts`, `hashSequence`, and `hashOutputs`. The preimage and digest follow BIP143 and respect the
selected `SIGHASH` and `ANYONECANPAY` commitments.

For P2MS, the response exposes the unlocking, locking, and combined scripts; required signature count; total public
key count; ordered serialized signatures and public keys; NULLDUMMY presence; and the real combined-script execution
trace through `OP_CHECKMULTISIG`. This endpoint does not provide a per-signature sighash walkthrough. Consumers must
label that boundary explicitly rather than presenting P2PKH verification data for a multisig spend.

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
