"""The vocabulary validator is what stops Gemini from silently promoting or demoting
people in the answer key. These run offline against hand-written "LLM output"."""

from orgchart.generator import vocabulary
from orgchart.generator.vocabulary import _validate, canonical_titles

CANON = canonical_titles()


def _check(title: str, variants: list[str]):
    keep, rejected = _validate(CANON, {title: variants})
    return keep[title], [r["variant"] for r in rejected.get(title, [])]


def test_same_level_rewordings_are_kept():
    kept, _ = _check("Head of Legal", ["Legal Director", "Head, Legal", "Director of Legal"])
    assert kept == ["Legal Director", "Head, Legal", "Director of Legal"]
    kept, _ = _check("Co-Founder & CEO", ["Chief Executive Officer & Co-Founder"])
    assert kept == ["Chief Executive Officer & Co-Founder"]


def test_promotions_and_demotions_are_rejected():
    _, rej = _check("VP Engineering", ["EVP Engineering", "SVP, Engineering", "Vice President, Engineering"])
    assert rej == ["EVP Engineering", "SVP, Engineering"]
    _, rej = _check("Engineering Manager", ["Engineering Lead", "Senior Engineering Manager", "Eng Mgr"])
    assert "Engineering Lead" in rej and "Eng Mgr" not in rej


def test_variant_that_is_another_canonical_title_is_rejected():
    _, rej = _check("Head of Data", ["Chief Data Officer", "Data Head"])
    assert rej == ["Chief Data Officer"]


def test_spelling_shared_across_levels_is_dropped_everywhere():
    keep, rejected = _validate(CANON, {"Store Manager": ["Retail Mgr"], "Area Manager": ["Retail Mgr"]})
    assert keep["Store Manager"] == [] and keep["Area Manager"] == []


def test_committed_vocab_covers_every_canonical_title():
    vocab = vocabulary.load()
    assert set(vocab) == set(CANON)
    assert all(len(v) >= 5 for v in vocab.values())
