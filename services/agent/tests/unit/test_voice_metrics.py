import pytest

from agent.audio.metrics import WordErrors, score_words


@pytest.mark.parametrize(
    "reference,hypothesis,errors,words",
    [
        ("Open the folder.", "open the folder", 0, 3),
        ("Open the policy folder", "open a folder", 2, 4),
        ("Open folder", "open the policy folder", 2, 2),
        ("Open folder", "", 2, 2),
        ("", "unexpected word", 2, 0),
    ],
)
def test_wer_function_matches_known_pairs(reference, hypothesis, errors, words):
    assert score_words(reference, hypothesis) == WordErrors(errors, words)


def test_corpus_wer_is_weighted_by_reference_word_count():
    a = score_words("one", "two")
    b = score_words("one two three four", "one two three four")
    assert WordErrors(a.errors + b.errors, a.words + b.words).wer == 0.2
    with pytest.raises(ValueError):
        _ = WordErrors(1, 0).wer
