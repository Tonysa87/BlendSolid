"""Milestone 2's success criterion (docs/spec.md): 95% of the faces and edges clicked on 20 parts produce a unique
reference that survives 3 upstream changes, and no reference silently binds to something else (design: zero silent
wrong bindings). Also measured: an unrelated feature inserted upstream. Harness: criterion.py; parts:
criterion_corpus.py. The share is over the 20 parts together (the spec's "on a set of 20 parts"); each part must
have no silent wrong binding. The table is printed with -s."""
import pytest

import criterion
from criterion_corpus import corpus

CASES = {c.name: c for c in corpus()}


def _changes(case):
    return criterion.score(criterion.run_changes(case.source, case.changes))


def _insert(case):
    before = criterion.Build(case.source)
    after = criterion.Build(criterion.insert_after_first(case.source, case.insert))
    assert len(after.faces) > len(before.faces), case.name  # the inserted hole is really there
    return criterion.score([before, after], mapping_of=lambda kind: criterion.identical(before, after, kind))


@pytest.fixture(scope="module")
def scores():
    out = {(name, label): run(case) for name, case in CASES.items() for label, run in (("changes", _changes),
                                                                                      ("insert", _insert))}
    print()
    for (name, label), s in sorted(out.items(), key=lambda kv: (kv[0][1], kv[0][0])):
        print(f"{name:18s} {label:8s} entities {s.total:4d} unique {s.unique:4d} tracked {s.tracked:4d} "
              f"ok {s.ok:4d} flagged {s.flagged:3d} wrong {len(s.wrong)}")
    return out


def test_corpus_has_20_parts():
    assert len(CASES) == 20


@pytest.mark.parametrize("label", ["changes", "insert"])
def test_no_silent_wrong_binding(scores, label):
    wrong = {name: s.wrong[:3] for (name, lab), s in scores.items() if lab == label and s.wrong}
    assert not wrong


@pytest.mark.parametrize("label", ["changes", "insert"])
def test_95_percent_survive(scores, label):
    tracked = sum(s.tracked for (_, lab), s in scores.items() if lab == label)
    ok = sum(s.ok for (_, lab), s in scores.items() if lab == label)
    lost = sum(s.total - s.tracked for (_, lab), s in scores.items() if lab == label)
    print(f"\n{label}: {ok}/{tracked} = {ok / tracked:.1%} survive (oracle lost {lost} entities)")
    assert ok / tracked >= 0.95


def test_every_click_names_its_entity(scores):
    # uniqueness at click time, on every part (the references' own guarantee, ADR 0009)
    assert {name: (s.unique, s.total) for (name, lab), s in scores.items() if lab == "changes" and s.unique < s.total} \
        == {}
