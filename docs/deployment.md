# Backend deployment runbook

This runbook is host-neutral. It applies to any platform that can run the repository's OCI image behind HTTPS and keep
at least one previous image available for rollback.

## Required platform configuration

- Run one immutable image built from the intended backend commit. Do not install a floating Bitclone revision at
  startup; the image build uses the commit pinned in `pyproject.toml`.
- Listen on container port 8000 unless the platform overrides the image command.
- Terminate TLS at the platform proxy and forward requests to the container over the platform's private network.
- Set the readiness and liveness endpoint to `GET /api/v1/health`.
- Set `BML_CORS_ORIGINS` to the exact HTTPS frontend origins, separated by commas. Never use a wildcard.
- Set `BML_RELEASE` to the candidate commit or immutable image identifier.
- Retain application logs long enough to correlate a reported `X-Request-ID`. Logs must remain access-controlled.

The MVP API does not require a database or application secret. Do not add credentials to the image, repository, build
arguments, or command history.

## Pre-deployment checklist

1. Confirm CI is green for the exact commit being deployed.
2. Record the candidate commit, image digest, current image digest, and UTC start time in the release record.
3. Confirm the current image is still available for rollback.
4. Confirm the frontend origin in `BML_CORS_ORIGINS` has no path or trailing slash.
5. Build the image locally if the platform does not build it:

   ```bash
   docker build --tag bitcoin-math-lab-backend:<commit> .
   ```

6. Exercise that exact image before publishing it:

   ```bash
   docker run --detach --name bml-backend-candidate --publish 8000:8000 \
     --env BML_CORS_ORIGINS=https://bitcoinmathlab.com --env BML_RELEASE=<commit> \
     bitcoin-math-lab-backend:<commit>
   python scripts/smoke_test.py --api-base-url http://127.0.0.1:8000 --expected-release <commit>
   docker rm --force bml-backend-candidate
   ```

## Rollout and verification

1. Deploy the candidate image without removing the previous image.
2. Wait for the platform health check to report healthy.
3. Run the API contract smoke check against the public HTTPS origin:

   ```bash
   python scripts/smoke_test.py --api-base-url https://api.btcmathlab.com --expected-release <commit>
   ```

4. Confirm a browser preflight from the production frontend origin returns that exact
   `Access-Control-Allow-Origin` value and exposes `X-Request-ID`.
5. Run the frontend production smoke command. It verifies the public shell and executes both successful and failing
   lessons through this API.
6. Confirm request records are present for the smoke requests and contain no query string, body, headers, or exception
   text.
7. Record the smoke result, deployed image digest, and UTC completion time.

## Rollback

Rollback is required if health checks fail, the API smoke check fails, browser CORS fails, or the visualizer cannot
complete both lessons.

1. Route traffic back to the previously recorded image digest.
2. Wait for health checks to pass.
3. Rerun `scripts/smoke_test.py` against the public origin.
4. Rerun the frontend production smoke command.
5. Record the failed candidate digest, request IDs from failures, rollback digest, and UTC times.

Because the MVP backend has no persistent state, rollback requires no data migration. Do not retry a failed rollout
with unreviewed changes; fix it through the normal pull-request and CI path.

## Incident evidence

Capture only the minimum information needed to diagnose a release:

- release commit and image digest;
- UTC timestamps and HTTP status codes;
- platform health events;
- the safe error code returned to the client; and
- `X-Request-ID` values and their matching structured request records.

Do not paste request bodies, query strings, cookies, authorization headers, complete platform environment dumps, or
internal exception messages into issues or chat.
