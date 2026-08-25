from types import SimpleNamespace

import pytest

from bml_backend.example_verification import (
    TransactionExampleMismatch,
    verify_transaction_examples,
)
from bml_backend.transaction_examples import TransactionExample


TXID = "11" * 32
EXAMPLE = TransactionExample(
    slug="verified-example",
    title="Verified example",
    description="A deterministic transaction context fixture.",
    txid=TXID,
    input_count=1,
    output_count=2,
    expected_spend_types=("P2WPKH",),
    concepts=("SegWit",),
)


class FakeSource:
    def __init__(self, context):
        self.context = context
        self.txids = []

    def load_context(self, txid):
        self.txids.append(txid)
        return self.context


def context(*, txid=TXID, inputs=1, outputs=2, spend_type="P2WPKH"):
    return SimpleNamespace(
        txid=txid,
        spent_outputs=tuple(SimpleNamespace(spend_type=spend_type) for _ in range(inputs)),
        outputs=tuple(SimpleNamespace() for _ in range(outputs)),
    )


def test_verifies_expected_transaction_shape_and_spend_types():
    source = FakeSource(context())

    assert verify_transaction_examples(source, [EXAMPLE]) == 1
    assert source.txids == [TXID]


@pytest.mark.parametrize(
    ("actual", "message"),
    [
        (context(txid="22" * 32), "transaction ID mismatch"),
        (context(outputs=1), "expected 1 inputs/2 outputs"),
        (context(spend_type="P2PKH"), "expected spend types"),
    ],
)
def test_rejects_catalog_drift(actual, message):
    with pytest.raises(TransactionExampleMismatch, match=message):
        verify_transaction_examples(FakeSource(actual), [EXAMPLE])
