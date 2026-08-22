# Standard script templates API

`POST /api/v1/scripts/templates` constructs standard mainnet locking scripts without requiring Bitcoin Core.

Request:

```json
{
  "template": "P2WPKH",
  "program_hex": "<20-byte public-key hash>"
}
```

Supported templates are P2SH, P2WPKH, P2WSH, P2TR-KEY-PATH, and P2TR-SCRIPT-PATH. P2SH/P2WPKH require 20-byte
programs; P2WSH and Taproot require 32-byte programs. Taproot accepts an already-tweaked, valid x-only output key.

The response includes the normalized program, script family, serialized scriptPubKey, and mainnet address. Taproot
key-path and script-path requests intentionally produce the same locking bytes while preserving the intended teaching
path as metadata.

Invalid template names and hex are rejected by the v1 request contract. Incorrect program lengths and invalid Taproot
keys return HTTP 422 with the stable `invalid-script-template` code.
