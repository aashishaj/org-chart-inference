"""Checks on the files the generator writes: what reviewers will open first."""

import csv
import filecmp
from collections import Counter

import pytest

from orgchart.generator.generate import PUBLIC_PEOPLE, generate


@pytest.fixture(scope="module")
def data(tmp_path_factory):
    out = tmp_path_factory.mktemp("data")
    generate(n_companies=15, seed=7, out=out)

    def read(name):
        with open(out / name, newline="") as f:
            return list(csv.DictReader(f))

    return out, {n: read(n) for n in ["companies.csv", "people.csv", "truth/people.csv", "truth/true_tree.csv",
                                      "truth/companies.csv"]}


def test_public_files_hold_no_answers(data):
    _, d = data
    assert list(d["people.csv"][0]) == PUBLIC_PEOPLE
    assert not {"manager", "expected_manager_id", "kind", "level"} & set(d["people.csv"][0])
    assert not {"mess_level", "inflated"} & set(d["companies.csv"][0])


def test_every_company_has_100_plus_visible_employees(data):
    _, d = data
    employees = Counter(r["company_id"] for r in d["truth/people.csv"] if r["kind"] == "employee")
    assert len(employees) == 15 and min(employees.values()) >= 100


def test_answer_key_is_consistent(data):
    _, d = data
    public = {r["record_id"]: r for r in d["people.csv"]}
    truth = {r["record_id"]: r for r in d["truth/people.csv"]}
    assert public.keys() == truth.keys(), "every public record has exactly one truth row"
    ghosts = {k for k, t in truth.items() if t["kind"] == "ghost"}
    for t in truth.values():
        if m := t["expected_manager_id"]:
            assert m in public and public[m]["company_id"] == t["company_id"]
            assert m not in ghosts
        if t["kind"] == "ghost":
            assert not t["expected_manager_id"]
    roots = Counter(t["company_id"] for t in truth.values() if t["kind"] == "employee" and not t["expected_manager_id"])
    assert set(roots.values()) == {1}, "exactly one visible top (the CEO) per company"


def test_ids_are_opaque_and_unique(data):
    _, d = data
    ids = [r["record_id"] for r in d["people.csv"]]
    assert len(ids) == len(set(ids)) and all(len(i) == 8 for i in ids)


def test_same_seed_same_bytes(data, tmp_path):
    out, _ = data
    generate(n_companies=15, seed=7, out=tmp_path)
    for name in ["people.csv", "truth/people.csv", "companies.csv"]:
        assert filecmp.cmp(out / name, tmp_path / name, shallow=False), name
