"""Build transport-neutral transaction execution context from Bitcoin Core."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from src.block import Block
from src.database.bitcoin_core_rpc import BitcoinCoreRPCError
from src.script import classify_spend
from src.tx import Tx


GENESIS_TXID = "4a5e1e4baab89f3a32518a88c31bc87f618f76673e2cc77ab2127b7afdeda33b"


class BitcoinCoreClient(Protocol):
    def get_raw_transaction(self, display_txid: str, verbose: bool = False): ...

    def get_block_hash(self, height: int) -> bytes: ...

    def get_block(self, block_hash: bytes) -> bytes: ...


@dataclass(frozen=True, slots=True)
class SpentOutputContext:
    txid: str
    vout: int
    amount_sats: int
    script_pubkey_hex: str
    output_type: str | None = None
    spend_type: str = "UNKNOWN"
    is_nested: bool = False
    redeem_script_hex: str | None = None


@dataclass(frozen=True, slots=True)
class TransactionOutputContext:
    vout: int
    amount_sats: int
    script_pubkey_hex: str


@dataclass(frozen=True, slots=True)
class TransactionContext:
    txid: str
    transaction_hex: str
    is_coinbase: bool
    outputs: tuple[TransactionOutputContext, ...]
    spent_outputs: tuple[SpentOutputContext, ...]


class TransactionContextSource(Protocol):
    def load_context(self, txid: str) -> TransactionContext: ...


class TransactionSourceError(Exception):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message

    def __str__(self) -> str:
        return self.message


class BitcoinCoreTransactionSource:
    """Load a transaction and the outputs spent by each input from Bitcoin Core."""

    def __init__(self, client: BitcoinCoreClient) -> None:
        self._client = client

    def load_context(self, txid: str) -> TransactionContext:
        normalized_txid = _normalize_txid(txid)
        transaction = self._load_transaction(normalized_txid)
        transaction_hex = transaction.to_bytes().hex()
        outputs = tuple(
            TransactionOutputContext(
                vout=vout,
                amount_sats=output.amount,
                script_pubkey_hex=output.scriptpubkey.hex(),
            )
            for vout, output in enumerate(transaction.outputs)
        )

        if transaction.is_coinbase:
            return TransactionContext(
                txid=normalized_txid,
                transaction_hex=transaction_hex,
                is_coinbase=True,
                outputs=outputs,
                spent_outputs=(),
            )

        previous_transactions: dict[str, Tx] = {}
        spent_outputs: list[SpentOutputContext] = []
        for input_index, transaction_input in enumerate(transaction.inputs):
            previous_txid = transaction_input.txid[::-1].hex()
            previous = previous_transactions.get(previous_txid)
            if previous is None:
                previous = self._load_transaction(previous_txid)
                previous_transactions[previous_txid] = previous

            if transaction_input.vout >= len(previous.outputs):
                raise TransactionSourceError(
                    "previous-output-missing",
                    "Bitcoin Core transaction data does not contain a referenced previous output.",
                )

            output = previous.outputs[transaction_input.vout]
            witness = (
                transaction.witness[input_index].items
                if input_index < len(transaction.witness)
                else ()
            )
            classification = classify_spend(
                output.scriptpubkey,
                script_sig=transaction_input.scriptsig,
                witness=witness,
            )
            spent_outputs.append(
                SpentOutputContext(
                    txid=previous_txid,
                    vout=transaction_input.vout,
                    amount_sats=output.amount,
                    script_pubkey_hex=output.scriptpubkey.hex(),
                    output_type=(
                        classification.output_type.value
                        if classification.output_type is not None
                        else None
                    ),
                    spend_type=classification.spend_type.value,
                    is_nested=classification.is_nested,
                    redeem_script_hex=(
                        classification.redeem_script.hex()
                        if classification.redeem_script is not None
                        else None
                    ),
                )
            )

        return TransactionContext(
            txid=normalized_txid,
            transaction_hex=transaction_hex,
            is_coinbase=False,
            outputs=outputs,
            spent_outputs=tuple(spent_outputs),
        )

    def _load_transaction(self, txid: str) -> Tx:
        try:
            raw_hex = self._client.get_raw_transaction(txid, False)
        except BitcoinCoreRPCError as exc:
            if txid == GENESIS_TXID:
                return self._load_genesis_transaction()
            raise TransactionSourceError(
                "bitcoin-core-unavailable",
                "Bitcoin Core could not provide the requested transaction.",
            ) from exc

        if not isinstance(raw_hex, str):
            raise TransactionSourceError(
                "invalid-source-data",
                "Bitcoin Core returned an invalid raw transaction response.",
            )
        try:
            raw = bytes.fromhex(raw_hex)
            transaction = Tx.from_bytes(raw)
        except Exception as exc:
            raise TransactionSourceError(
                "invalid-source-data",
                "Bitcoin Core returned an invalid raw transaction response.",
            ) from exc

        if transaction.to_bytes() != raw or transaction.txid[::-1].hex() != txid:
            raise TransactionSourceError(
                "invalid-source-data",
                "Bitcoin Core returned transaction data that does not match the requested txid.",
            )
        return transaction

    def _load_genesis_transaction(self) -> Tx:
        """Load block zero because Core excludes its coinbase from getrawtransaction."""
        try:
            block_hash = self._client.get_block_hash(0)
            raw_block = self._client.get_block(block_hash)
            block = Block.from_bytes(raw_block)
        except BitcoinCoreRPCError as exc:
            raise TransactionSourceError(
                "bitcoin-core-unavailable",
                "Bitcoin Core could not provide the requested transaction.",
            ) from exc
        except Exception as exc:
            raise TransactionSourceError(
                "invalid-source-data",
                "Bitcoin Core returned invalid genesis block data.",
            ) from exc

        if (
            block.to_bytes() != raw_block
            or block.block_id != block_hash
            or len(block.txs) != 1
            or block.txs[0].txid[::-1].hex() != GENESIS_TXID
        ):
            raise TransactionSourceError(
                "invalid-source-data",
                "Bitcoin Core returned invalid genesis block data.",
            )
        return block.txs[0]


def _normalize_txid(txid: str) -> str:
    normalized = txid.strip().lower()
    if len(normalized) != 64:
        raise TransactionSourceError("invalid-txid", "txid must contain exactly 32 bytes of hex.")
    try:
        bytes.fromhex(normalized)
    except ValueError as exc:
        raise TransactionSourceError(
            "invalid-txid", "txid must contain exactly 32 bytes of hex."
        ) from exc
    return normalized
