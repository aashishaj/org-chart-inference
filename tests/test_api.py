"""The web API on a small generated dataset, split per company the way the app serves it."""

import pytest
from fastapi.testclient import TestClient

from orgchart.api import store
from orgchart.generator.generate import generate


@pytest.fixture(scope="module")
def client(tmp_path_factory):
    data = tmp_path_factory.mktemp("data")
    generate(n_companies=3, seed=11, out=data)
    split_dir = data / "by_company"
    store.split(data, split_dir)
    mp = pytest.MonkeyPatch()
    mp.setattr(store, "SPLIT_DIR", split_dir)
    for f in (store.company_index, store.company_ids, store.view, store.answer_key):
        f.cache_clear()
    from orgchart.api.app import app
    yield TestClient(app)
    mp.undo()
    for f in (store.company_index, store.company_ids, store.view, store.answer_key):
        f.cache_clear()


@pytest.fixture(scope="module")
def cid(client):
    return client.get("/api/companies").json()[0]["company_id"]


def test_company_list_and_search(client):
    companies = client.get("/api/companies").json()
    assert len(companies) == 3 and all(c["records"] >= 100 for c in companies)
    name = companies[0]["name"]
    assert [c["name"] for c in client.get("/api/companies", params={"q": name[:5].lower()}).json()].count(name) == 1


def test_chart_has_one_answer_per_record_and_valid_managers(client, cid):
    d = client.get(f"/api/companies/{cid}/chart").json()
    ids = {p["id"] for p in d["people"]}
    assert len(ids) == len(d["people"]) == next(c["records"] for c in client.get("/api/companies").json()
                                                 if c["company_id"] == cid)
    for p in d["people"]:
        assert (p["manager_id"] is None) == (p["placement"] in ("root", "unplaced"))
        assert p["manager_id"] is None or p["manager_id"] in ids
    assert sum(d["counts"].values()) == len(d["people"])


def test_looser_presets_place_more_people(client, cid):
    placed = {pr: sum(1 for p in client.get(f"/api/companies/{cid}/chart", params={"preset": pr}).json()["people"]
                      if p["manager_id"]) for pr in ("strict", "balanced", "broad")}
    assert placed["strict"] <= placed["balanced"] <= placed["broad"]
    assert client.get(f"/api/companies/{cid}/chart", params={"preset": "reckless"}).status_code == 400


def test_why_explains_the_decision(client, cid):
    people = client.get(f"/api/companies/{cid}/chart", params={"preset": "broad"}).json()["people"]
    p = next(p for p in people if p["placement"] == "exact")
    d = client.get(f"/api/companies/{cid}/people/{p['id']}/why", params={"preset": "broad"}).json()
    assert d["decision"]["manager"]["id"] == p["manager_id"] == d["candidates"][0]["id"]
    probs = [c["probability"] for c in d["candidates"]]
    assert probs == sorted(probs, reverse=True) and sum(probs) + d["probability_no_boss_here"] <= 1.001


def test_grade_matches_the_chart(client, cid):
    chart = client.get(f"/api/companies/{cid}/chart").json()["people"]
    g = client.get(f"/api/companies/{cid}/grade").json()
    assert set(g["lines"]) == {p["id"] for p in chart}
    claims = sum(1 for p in chart if p["manager_id"])
    assert g["scorecard"]["claims"] == claims
    assert g["scorecard"]["wrong"] == sum(1 for line in g["lines"].values() if line["wrong"])
    assert g["split"] in ("train", "dev", "test")


def test_unknown_company_is_404(client):
    assert client.get("/api/companies/NOPE/chart").status_code == 404
    assert client.get("/api/companies/NOPE/grade").status_code == 404


def test_ask_is_off_without_a_key(client, cid, monkeypatch):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    assert client.get("/api/ask").json() == {"enabled": False}
    assert client.post(f"/api/companies/{cid}/ask", json={"question": "Who leads sales?"}).status_code == 503
