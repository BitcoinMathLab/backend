from collections import Counter

import pytest
from src.database.bitcoin_core_rpc import BitcoinCoreRPCError
from src.tx import Tx, TxIn, TxOut

from bml_backend.bitcoin_core import BitcoinCoreTransactionSource, TransactionSourceError


class FakeBitcoinCore:
    def __init__(self, transactions):
        self.transactions = transactions
        self.calls = Counter()

    def get_raw_transaction(self, display_txid, verbose=False):
        assert verbose is False
        self.calls[display_txid] += 1
        value = self.transactions[display_txid]
        if isinstance(value, Exception):
            raise value
        return value


def transaction_hex(transaction):
    return transaction.to_bytes().hex()


def display_txid(transaction):
    return transaction.txid[::-1].hex()


def coinbase_transaction(outputs):
    return Tx(
        inputs=[TxIn(b"\x00" * 32, 0xFFFFFFFF, b"coinbase", 0xFFFFFFFF)],
        outputs=outputs,
    )


def test_loads_transaction_and_ordered_previous_output_context():
    previous = coinbase_transaction(
        [
            TxOut(1_500, bytes.fromhex("51")),
            TxOut(2_500, bytes.fromhex("76a914" + "11" * 20 + "88ac")),
        ]
    )
    target = Tx(
        inputs=[
            TxIn(previous.txid, 1, b"\x51", 0xFFFFFFFE),
            TxIn(previous.txid, 0, b"\x51", 0xFFFFFFFD),
        ],
        outputs=[TxOut(3_500, bytes.fromhex("51"))],
    )
    client = FakeBitcoinCore(
        {
            display_txid(target): transaction_hex(target),
            display_txid(previous): transaction_hex(previous),
        }
    )

    context = BitcoinCoreTransactionSource(client).load_context(display_txid(target).upper())

    assert context.txid == display_txid(target)
    assert context.transaction_hex == transaction_hex(target)
    assert context.is_coinbase is False
    actual_outputs = [
        (output.vout, output.amount_sats, output.script_pubkey_hex)
        for output in context.spent_outputs
    ]
    assert actual_outputs == [
        (1, 2_500, "76a914" + "11" * 20 + "88ac"),
        (0, 1_500, "51"),
    ]
    assert client.calls[display_txid(previous)] == 1


def test_coinbase_context_has_no_previous_outputs():
    coinbase = coinbase_transaction([TxOut(5_000_000_000, bytes.fromhex("51"))])
    client = FakeBitcoinCore({display_txid(coinbase): transaction_hex(coinbase)})

    context = BitcoinCoreTransactionSource(client).load_context(display_txid(coinbase))

    assert context.is_coinbase is True
    assert context.spent_outputs == ()


@pytest.mark.parametrize("txid", ["", "00", "gg" * 32])
def test_rejects_invalid_transaction_ids_before_rpc(txid):
    client = FakeBitcoinCore({})

    with pytest.raises(TransactionSourceError, match="32 bytes") as error:
        BitcoinCoreTransactionSource(client).load_context(txid)

    assert error.value.code == "invalid-txid"
    assert client.calls == Counter()


def test_wraps_rpc_failure_without_exposing_core_detail():
    txid = "11" * 32
    client = FakeBitcoinCore({txid: BitcoinCoreRPCError("password=private connection refused")})

    with pytest.raises(TransactionSourceError) as error:
        BitcoinCoreTransactionSource(client).load_context(txid)

    assert error.value.code == "bitcoin-core-unavailable"
    assert "private" not in str(error.value)


def test_rejects_previous_output_index_missing_from_source_transaction():
    previous = coinbase_transaction([TxOut(1_500, bytes.fromhex("51"))])
    target = Tx(
        inputs=[TxIn(previous.txid, 2, b"\x51", 0xFFFFFFFE)],
        outputs=[TxOut(1_000, bytes.fromhex("51"))],
    )
    client = FakeBitcoinCore(
        {
            display_txid(target): transaction_hex(target),
            display_txid(previous): transaction_hex(previous),
        }
    )

    with pytest.raises(TransactionSourceError) as error:
        BitcoinCoreTransactionSource(client).load_context(display_txid(target))

    assert error.value.code == "previous-output-missing"


def test_rejects_transaction_data_for_a_different_txid():
    requested_txid = "11" * 32
    different = coinbase_transaction([TxOut(1_500, bytes.fromhex("51"))])
    client = FakeBitcoinCore({requested_txid: transaction_hex(different)})

    with pytest.raises(TransactionSourceError, match="does not match") as error:
        BitcoinCoreTransactionSource(client).load_context(requested_txid)

    assert error.value.code == "invalid-source-data"
