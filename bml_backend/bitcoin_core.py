"""Build transport-neutral transaction execution context from Bitcoin Core."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from src.database.bitcoin_core_rpc import BitcoinCoreRPCError
from src.tx import Tx


class BitcoinCoreClient(Protocol):
    def get_raw_transaction(self, display_txid: str, verbose: bool = False): ...


@dataclass(frozen=True, slots=True)
class SpentOutputContext:
    txid: str
    vout: int
    amount_sats: int
    script_pubkey_hex: str


@dataclass(frozen=True, slots=True)
class TransactionContext:
    txid: str
    transaction_hex: str
    is_coinbase: bool
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

        if transaction.is_coinbase:
            return TransactionContext(
                txid=normalized_txid,
                transaction_hex=transaction_hex,
                is_coinbase=True,
                spent_outputs=(),
            )

        previous_transactions: dict[str, Tx] = {}
        spent_outputs: list[SpentOutputContext] = []
        for transaction_input in transaction.inputs:
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
            spent_outputs.append(
                SpentOutputContext(
                    txid=previous_txid,
                    vout=transaction_input.vout,
                    amount_sats=output.amount,
                    script_pubkey_hex=output.scriptpubkey.hex(),
                )
            )

        return TransactionContext(
            txid=normalized_txid,
            transaction_hex=transaction_hex,
            is_coinbase=False,
            spent_outputs=tuple(spent_outputs),
        )

    def _load_transaction(self, txid: str) -> Tx:
        try:
            raw_hex = self._client.get_raw_transaction(txid, False)
        except BitcoinCoreRPCError as exc:
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
