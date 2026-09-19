"""Bounded block lookup over the existing Bitcoin Core transport."""
from __future__ import annotations

import re
from typing import Annotated, Protocol

from pydantic import BaseModel, ConfigDict, Field, StringConstraints
from src.data import bits_to_target
from src.database.bitcoin_core_rpc import BitcoinCoreRPCError

from bml_backend.bitcoin_core import TransactionSourceError
from bml_backend.models import APIModel

Hash = Annotated[str, StringConstraints(pattern=r"^[0-9a-f]{64}$")]


class BlockMoney(APIModel):
    subsidy_sats: str
    fees_sats: str
    transaction_output_sats: str


class CoreBlockStats(BaseModel):
    model_config = ConfigDict(strict=True)
    blockhash: Hash
    height: int = Field(ge=0)
    subsidy: int = Field(ge=0)
    totalfee: int = Field(ge=0)
    total_out: int = Field(ge=0)


class BlockResponse(APIModel):
    block_hash: Hash
    height: int
    confirmations: int
    version: int
    merkle_root: Hash
    timestamp: int
    median_time: int
    bits: str
    target_hex: Hash
    money: BlockMoney | None
    nonce: int
    previous_block_hash: Hash | None
    next_block_hash: Hash | None
    size_bytes: int
    weight_units: int
    transaction_count: int
    transaction_ids: list[Hash]
    offset: int
    limit: int
    next_offset: int | None


class CoreBlock(BaseModel):
    """Validate upstream metadata; ignore Core's additional response fields."""

    model_config = ConfigDict(strict=True)
    hash: Hash
    height: int = Field(ge=0)
    confirmations: int = Field(ge=-1)
    version: int
    merkleroot: Hash
    time: int = Field(ge=0)
    mediantime: int = Field(ge=0)
    bits: Annotated[str, StringConstraints(pattern=r"^[0-9a-f]{8}$")]
    nonce: int = Field(ge=0, le=0xFFFFFFFF)
    previousblockhash: Hash | None = None
    nextblockhash: Hash | None = None
    size: int = Field(gt=0)
    weight: int = Field(gt=0)
    nTx: int = Field(gt=0)
    tx: list[Hash]


class BlockClient(Protocol):
    def call(self, method: str, *params): ...


class BlockSource(Protocol):
    def load_block(self, identifier: str | int, offset: int, limit: int) -> BlockResponse: ...


class BitcoinCoreBlockSource:
    def __init__(self, client: BlockClient) -> None:
        self._client = client

    def load_block(self, identifier: str | int, offset: int, limit: int) -> BlockResponse:
        if offset < 0 or not 1 <= limit <= 100:
            raise TransactionSourceError("request-validation", "Invalid block pagination.")
        if isinstance(identifier, str):
            identifier = identifier.strip().lower()
            if not re.fullmatch(r"[0-9a-f]{64}", identifier):
                raise TransactionSourceError("invalid-block-hash", "Block hash must contain 64 hex characters.")
        elif identifier < 0:
            raise TransactionSourceError("request-validation", "Block height must be nonnegative.")
        try:
            block_hash = (
                self._client.call("getblockhash", identifier)
                if isinstance(identifier, int)
                else identifier
            )
            if not isinstance(block_hash, str) or not re.fullmatch(r"[0-9a-f]{64}", block_hash):
                raise ValueError("Invalid block hash")
            block = CoreBlock.model_validate(self._client.call("getblock", block_hash, 1))
            compact = bytes.fromhex(block.bits)
            if compact[0] < 3 or compact[1] & 0x80 or int.from_bytes(compact[1:], "big") == 0:
                raise ValueError("Invalid mainnet compact target")
            target_hex = bits_to_target(bytes.fromhex(block.bits)).hex()
            if block.hash != block_hash or len(block.tx) != block.nTx:
                raise ValueError("Inconsistent block response")
            if isinstance(identifier, int) and block.height != identifier:
                raise ValueError("Incorrect block height")
        except BitcoinCoreRPCError as exc:
            raise TransactionSourceError(
                "bitcoin-core-unavailable", "Bitcoin Core could not provide the requested block."
            ) from exc
        except (ValueError, OverflowError) as exc:
            raise TransactionSourceError(
                "invalid-source-data", "Bitcoin Core returned invalid block data."
            ) from exc
        # Stats cover the whole block, independently of the transaction-ID page.
        # Preserve metadata when a node cannot supply historical statistics.
        money = None
        try:
            stats = CoreBlockStats.model_validate(self._client.call(
                "getblockstats", block.hash,
                ["blockhash", "height", "subsidy", "totalfee", "total_out"],
            ))
            if stats.blockhash != block.hash or stats.height != block.height:
                raise ValueError("Inconsistent block statistics")
            money = BlockMoney(
                subsidy_sats=str(stats.subsidy), fees_sats=str(stats.totalfee),
                transaction_output_sats=str(stats.total_out),
            )
        except (BitcoinCoreRPCError, ValueError):
            pass
        end = min(offset + limit, block.nTx)
        return BlockResponse(
            block_hash=block.hash, height=block.height, confirmations=block.confirmations,
            version=block.version, merkle_root=block.merkleroot, timestamp=block.time,
            median_time=block.mediantime, bits=block.bits, nonce=block.nonce,
            target_hex=target_hex, money=money,
            previous_block_hash=block.previousblockhash, next_block_hash=block.nextblockhash,
            size_bytes=block.size, weight_units=block.weight, transaction_count=block.nTx,
            transaction_ids=block.tx[offset:end], offset=offset, limit=limit,
            next_offset=end if end < block.nTx else None,
        )
