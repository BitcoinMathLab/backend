"""Stable educational examples for the real-transaction explorer."""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class TransactionExample:
    slug: str
    title: str
    description: str
    txid: str
    input_count: int
    output_count: int
    expected_spend_types: tuple[str, ...]
    concepts: tuple[str, ...]


TRANSACTION_EXAMPLES = (
    TransactionExample(
        slug="genesis-coinbase",
        title="Genesis coinbase",
        description="Inspect Bitcoin's block-zero coinbase and the output it created.",
        txid="4a5e1e4baab89f3a32518a88c31bc87f618f76673e2cc77ab2127b7afdeda33b",
        input_count=0,
        output_count=1,
        expected_spend_types=(),
        concepts=("coinbase", "block zero", "created output"),
    ),
    TransactionExample(
        slug="early-payment-and-change",
        title="Early payment and change",
        description="Compare one legacy P2PKH input with its payment and change outputs.",
        txid="fff2525b8931402dd09222c50775608f75787bd2b87e56995a7bdd30f79702c4",
        input_count=1,
        output_count=2,
        expected_spend_types=("P2PKH",),
        concepts=("P2PKH", "payment", "change"),
    ),
    TransactionExample(
        slug="legacy-p2pkh",
        title="Legacy P2PKH spend",
        description="Follow a classic pay-to-public-key-hash input and its two outputs.",
        txid="40e331b67c0fe7750bb3b1943b378bf702dce86124dc12fa5980f975db7ec930",
        input_count=1,
        output_count=2,
        expected_spend_types=("P2PKH",),
        concepts=("legacy", "P2PKH", "scriptSig"),
    ),
    TransactionExample(
        slug="native-segwit-p2wpkh",
        title="Native SegWit P2WPKH",
        description="See signature data move from scriptSig into the witness structure.",
        txid="242b2de161deac31f77238b898e85a5e4760c5aa004ede2e2cc355202f84e6aa",
        input_count=1,
        output_count=1,
        expected_spend_types=("P2WPKH",),
        concepts=("SegWit", "P2WPKH", "witness"),
    ),
    TransactionExample(
        slug="native-segwit-p2wsh",
        title="Native SegWit P2WSH",
        description="Inspect a witness-script-hash spend and its ordered output context.",
        txid="ed25927576988e38e4cc8e4b19d1272c480f113fb605271b190df05aa983714e",
        input_count=1,
        output_count=2,
        expected_spend_types=("P2WSH",),
        concepts=("SegWit", "P2WSH", "witness script"),
    ),
)
