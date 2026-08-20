# Bitcoin Math Lab Backend

FastAPI product API for Bitcoin Math Lab. The backend owns HTTP validation and product orchestration while reusable
Bitcoin execution remains in the sibling [Bitclone](https://github.com/BitcoinMathLab/bitclone) repository.

## Story 9.3 — P2PKH trace API

The first product endpoint executes one legacy P2PKH transaction input and returns the immutable Bitclone trace:

```text
POST /api/v1/traces/p2pkh
```

The request contains a serialized transaction, the input to inspect, and one spent-output descriptor per transaction
input. Supplying the complete spent-output list preserves the context required by Bitcoin signature validation and
allows the contract to grow toward SegWit and Taproot without changing its basic shape.

The endpoint returns normal script failures as HTTP 200 trace results with `success: false`. Malformed or unsupported
requests return a stable HTTP 422 error object. Python tracebacks and exception class names are never returned.

## Local development

Python 3.12 and a sibling Bitclone checkout are required:

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -e ../bitclone
.venv/bin/python -m pip install -e '.[dev]'
.venv/bin/uvicorn bml_backend.app:app --reload
```

OpenAPI is available at `http://127.0.0.1:8000/api/v1/openapi.json` and interactive documentation at
`http://127.0.0.1:8000/docs`.

## Validation

```bash
.venv/bin/python -m pytest -q
```
