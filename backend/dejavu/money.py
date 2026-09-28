"""Rupee amounts the way Kestrel Pay's engineers write them (lakh and crore)."""

LAKH = 100_000
CRORE = 10_000_000


def inr_words(amount: float) -> str:
    """`₹28.5 lakh` below one crore, `₹2.37 crore` above."""
    if amount >= CRORE:
        return f"₹{amount / CRORE:.2f} crore"
    return f"₹{amount / LAKH:.1f} lakh"
