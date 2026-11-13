"""Corpus WER: case and punctuation normalized, no external scoring service."""

from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass(frozen=True)
class WordErrors:
    errors: int
    words: int

    @property
    def wer(self) -> float:
        if self.words == 0:
            raise ValueError("WER requires a nonempty reference corpus")
        return self.errors / self.words


def score_words(reference: str, hypothesis: str) -> WordErrors:
    expected = re.findall(r"[\w]+(?:'[\w]+)*", reference.lower())
    actual = re.findall(r"[\w]+(?:'[\w]+)*", hypothesis.lower())
    previous = list(range(len(actual) + 1))
    for row, word in enumerate(expected, start=1):
        current = [row]
        for column, other in enumerate(actual, start=1):
            current.append(
                min(current[-1] + 1, previous[column] + 1, previous[column - 1] + (word != other))
            )
        previous = current
    return WordErrors(errors=previous[-1], words=len(expected))
