"""Verify the educational catalog through the configured Bitcoin Core source."""
from __future__ import annotations

from bml_backend.config import transaction_source_from_environment
from bml_backend.example_verification import verify_transaction_examples


def main() -> int:
    source = transaction_source_from_environment()
    if source is None:
        raise SystemExit("Bitcoin Core RPC configuration is required")
    count = verify_transaction_examples(source)
    print(f"Verified {count} educational transaction examples")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
