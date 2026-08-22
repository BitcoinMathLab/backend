"""Verify educational transaction metadata against a transaction context source."""
from __future__ import annotations

from collections.abc import Sequence

from bml_backend.bitcoin_core import TransactionContextSource
from bml_backend.transaction_examples import TRANSACTION_EXAMPLES, TransactionExample


class TransactionExampleMismatch(ValueError):
    """Raised when live transaction context has drifted from the catalog."""


def verify_transaction_examples(
    source: TransactionContextSource,
    examples: Sequence[TransactionExample] = TRANSACTION_EXAMPLES,
) -> int:
    """Load and compare every example, returning the verified example count."""
    for example in examples:
        context = source.load_context(example.txid)
        actual_spend_types = tuple(output.spend_type for output in context.spent_outputs)
        actual_shape = (len(context.spent_outputs), len(context.outputs))
        expected_shape = (example.input_count, example.output_count)

        if context.txid != example.txid:
            raise TransactionExampleMismatch(f"{example.slug}: transaction ID mismatch")
        if actual_shape != expected_shape:
            raise TransactionExampleMismatch(
                f"{example.slug}: expected {expected_shape[0]} inputs/{expected_shape[1]} outputs, "
                f"received {actual_shape[0]} inputs/{actual_shape[1]} outputs"
            )
        if actual_spend_types != example.expected_spend_types:
            raise TransactionExampleMismatch(
                f"{example.slug}: expected spend types {example.expected_spend_types}, "
                f"received {actual_spend_types}"
            )

    return len(examples)
