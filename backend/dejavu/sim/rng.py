"""Deterministic randomness. Every stream is derived from (seed, *labels), never from global state.

Python's built-in `hash()` is salted per process, so labels are hashed with SHA-256 instead.
"""

import hashlib
import random
import string

import numpy as np


def stable_hash(*parts: object) -> int:
    """A 64-bit hash of the parts that is identical across processes and platforms."""
    digest = hashlib.sha256("\x1f".join(str(p) for p in parts).encode()).digest()
    return int.from_bytes(digest[:8], "big")


def np_rng(seed: int, *labels: object) -> np.random.Generator:
    """An independent numpy stream for one purpose (e.g. `np_rng(42, "INC-4127", "metrics")`)."""
    return np.random.Generator(np.random.PCG64(np.random.SeedSequence([seed, stable_hash(*labels)])))


def py_rng(seed: int, *labels: object) -> random.Random:
    """An independent stdlib stream, for choices over Python objects."""
    return random.Random(stable_hash(seed, *labels))


def hex_id(rng: random.Random, length: int) -> str:
    return "".join(rng.choice("0123456789abcdef") for _ in range(length))


def pod_suffix(rng: random.Random) -> str:
    """Kubernetes-style 5-character pod suffix (consonants and digits, like the real generator)."""
    alphabet = "bcdfghjklmnpqrstvwxz2456789"
    return "".join(rng.choice(alphabet) for _ in range(5))


def replicaset_hash(rng: random.Random) -> str:
    """Kubernetes-style ReplicaSet hash (9-10 characters)."""
    alphabet = string.digits + "bcdfghjklmnpqrstvwxz"
    return "".join(rng.choice(alphabet) for _ in range(rng.choice((9, 10))))
