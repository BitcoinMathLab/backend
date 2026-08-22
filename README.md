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

## Story 11.1 — Bitcoin Core transaction context

When a local Bitcoin Core source is configured, the backend can load a real transaction and the previous output spent
by each input:

```text
GET /api/v1/transactions/{txid}/context
```

For local development through Bitclone's SSH tunnel, start the tunnel and backend with:

```bash
cd ../bitclone
./.venv/bin/python startup.py
cd ../backend
BML_CORE_RPC_URL=http://127.0.0.1:18332 \
  BML_CORE_RPC_COOKIE=~/.bitclone/skyscraper.cookie \
  .venv/bin/uvicorn bml_backend.app:app --reload
```

The Core node must have a synchronized transaction index for arbitrary historical txid lookup. When Core is absent or
still indexing, the endpoint returns a stable HTTP 503 response instead of exposing RPC details. Username/password RPC
authentication is also supported through `BML_CORE_RPC_USER` and `BML_CORE_RPC_PASSWORD`; credentials must never be
placed in the RPC URL or committed to the repository. `BML_CORE_RPC_TIMEOUT` defaults to 10 seconds.

Each previous output also includes its standard output family and observed spend path. This distinguishes legacy,
native and nested SegWit, and Taproot key-path/script-path spends without treating classification as script validation.

## Runtime configuration

The service is safe to run without browser cross-origin access. When the frontend and API use different origins, set
`BML_CORS_ORIGINS` to the exact comma-separated frontend origins that may call the API:

```bash
BML_CORS_ORIGINS=https://bitcoinmathlab.com,https://www.bitcoinmathlab.com \
  .venv/bin/uvicorn bml_backend.app:app --host 0.0.0.0 --port 8000
```

Wildcard origins are not accepted. Preview deployments should add only the specific preview origin being tested.
Set `BML_RELEASE` to the deployed commit or immutable image identifier. The health endpoint exposes this public value so
release smoke checks can reject a stale or unexpected image.

Every response includes an `X-Request-ID`. The service emits one compact JSON log record containing the request ID,
method, path, status, and duration, but never the query string or request body. Unexpected failures return a stable HTTP
500 error containing the same request ID, allowing an operator to correlate a browser report without exposing internal
exception messages.

## Local development

Python 3.12 is required. The package pins the tested Bitclone commit, so a sibling checkout is optional:

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -e '.[dev]'
.venv/bin/uvicorn bml_backend.app:app --reload
```

For simultaneous local engine work, install the sibling checkout after installing the backend:

```bash
.venv/bin/python -m pip install -e ../bitclone
```

OpenAPI is available at `http://127.0.0.1:8000/api/v1/openapi.json` and interactive documentation at
`http://127.0.0.1:8000/docs`.

## Validation

```bash
.venv/bin/python -m pytest -q
```

## Container deployment

The included `Dockerfile` builds a non-root, vendor-neutral service image and listens on port 8000. Deploy it behind an
HTTPS reverse proxy, configure the platform health check to call `/api/v1/health`, and set `BML_CORS_ORIGINS` to the
deployed frontend origin. Platforms that inject a different port can override the image command.

Run the production smoke check against any deployed API origin:

```bash
python scripts/smoke_test.py --api-base-url https://api.btcmathlab.com --expected-release <commit>
```

The check waits for health readiness, then executes the curated valid and invalid P2PKH examples and verifies the
versioned trace contract and correlation headers. CI runs it against the freshly built container image.

See the [deployment runbook](docs/deployment.md) for the release, verification, rollback, and incident checklist.
