"""Cryptographic primitives: unique tokens, hash-chain, Merkle trees."""
from __future__ import annotations

import hashlib
import secrets

GENESIS = "0" * 64


def sha256(data: str) -> str:
    return hashlib.sha256(data.encode("utf-8")).hexdigest()


def canonical(sender: str, receiver: str, amount_paise: int, parent: str | None, purpose: str, ts: int) -> str:
    return f"{sender}|{receiver}|{amount_paise}|{parent or ''}|{purpose}|{ts}"


def new_token(payload: str) -> str:
    """Unique per transaction: bound to the payload AND 128 bits of fresh randomness."""
    return sha256(payload + "|" + secrets.token_hex(16))


def link_hash(prev_hash: str, token: str, payload: str) -> str:
    return sha256(f"{prev_hash}|{token}|{payload}")


def merkle_root(leaves: list[str]) -> str:
    if not leaves:
        return GENESIS
    level = list(leaves)
    while len(level) > 1:
        if len(level) % 2:
            level.append(level[-1])
        level = [sha256(level[i] + level[i + 1]) for i in range(0, len(level), 2)]
    return level[0]


def merkle_proof(leaves: list[str], index: int) -> list[dict]:
    """Sibling path proving leaves[index] belongs to the root."""
    proof, level, i = [], list(leaves), index
    while len(level) > 1:
        if len(level) % 2:
            level.append(level[-1])
        sib = i ^ 1
        proof.append({"hash": level[sib], "position": "left" if sib < i else "right"})
        level = [sha256(level[j] + level[j + 1]) for j in range(0, len(level), 2)]
        i //= 2
    return proof


def verify_proof(leaf: str, proof: list[dict], root: str) -> bool:
    h = leaf
    for step in proof:
        h = sha256(step["hash"] + h) if step["position"] == "left" else sha256(h + step["hash"])
    return h == root
