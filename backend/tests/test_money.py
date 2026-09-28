"""Rupee amounts in lakh and crore, as Kestrel Pay's engineers write them."""

import pytest

from dejavu.money import inr_words


@pytest.mark.parametrize(
    ("amount", "words"),
    [
        (2_850_000, "₹28.5 lakh"),
        (23_700_000, "₹2.37 crore"),
        (0, "₹0.0 lakh"),
        (-1_250_000, "-₹12.5 lakh"),
    ],
)
def test_inr_words(amount: float, words: str) -> None:
    assert inr_words(amount) == words
