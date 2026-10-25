from types import SimpleNamespace

import pytest

from orgchart import llm
from orgchart.api import ask


def person(rid, name, title, level, function, manager=None, placement="exact", confidence=0.9, **extra):
    return {"id": rid, "name": name, "title": title, "department": "", "location": "Sydney", "start_date": "2020-01",
            "level": level, "function": function, "manager_id": manager, "placement": placement,
            "confidence": confidence, **extra}


@pytest.fixture
def chart():
    people = [
        person("ceo", "Ann Lee", "CEO", "CEO", "executive", placement="root", confidence=0),
        person("cto", "Bo Chan", "Chief Technology Officer", "C-suite", "engineering", "ceo"),
        person("em", "Cy Diaz", "Engineering Manager", "Manager", "engineering", "cto", "partial", 0.8),
        person("dev", "Di Eng", "Software Engineer", "IC", "engineering", "em"),
        person("lost", "Ed Fox", "Analyst", "IC", "data", placement="unplaced", confidence=0.3,
               best_guess_id="cto", best_guess_p=0.42),
    ]
    return ask.Chart({"name": "Testco"}, {p["id"]: p for p in people})


def test_find_people_matches_all_words_and_filters(chart):
    assert [p["id"] for p in chart.find_people("chief technology")["people"]] == ["cto"]
    assert {p["id"] for p in chart.find_people(department="engineering")["people"]} == {"cto", "em", "dev"}
    assert chart.find_people(level="IC", department="data")["people"][0]["line"] == \
        "not placed; best guess [[cto|Bo Chan]] (42%)"


def test_person_separates_direct_reports_from_somewhere_under(chart):
    p = chart.person("cto")
    assert p["direct_reports"] == [] and [r["id"] for r in p["somewhere_under_them"]] == ["em"]
    assert p["everyone_under_them"] == 2 and p["chain_up"] == ["[[ceo|Ann Lee]]"]
    assert chart.person("nobody") == {"error": "no person nobody"}


def test_people_under_and_biggest_teams(chart):
    assert chart.people_under("ceo", level="IC")["total"] == 1
    assert chart.company_overview()["biggest_teams"][0]["id"] == "ceo"


def test_links_to_people_never_looked_up_are_unlinked(chart):
    chart.find_people("chief")
    text = "[[cto|Bo Chan]] manages [[ghost|Zed]] and [[dev|Di Eng]]."
    assert ask._clean(text, chart) == "[[cto|Bo Chan]] manages Zed and Di Eng."


def test_rate_limit_per_visitor_and_per_day(monkeypatch):
    monkeypatch.setattr(ask, "_visits", ask.defaultdict(ask.deque))
    monkeypatch.setattr(ask, "_day", {"date": "", "count": 0})
    n, window = ask.PER_VISITOR
    assert all(ask.allow("a", now=1000 + i) is None for i in range(n))
    assert ask.allow("a", now=1000 + n) is not None
    assert ask.allow("b", now=1000 + n) is None
    assert ask.allow("a", now=1000 + window + 1) is None
    monkeypatch.setattr(ask, "_day", {"date": "1970-01-01", "count": ask.PER_DAY})
    assert "daily" in ask.allow("c", now=1000)


def test_cache_key_ignores_case_spacing_and_punctuation():
    assert ask.cache_key("C1", "strict", "Who leads  Sales?") == ask.cache_key("C1", "strict", "who leads sales")
    assert ask.cache_key("C1", "strict", "who leads sales") != ask.cache_key("C1", "broad", "who leads sales")


class FakeModels:
    """Asks for one tool call, then answers with what it found."""

    def __init__(self):
        self.calls = 0

    def generate_content(self, model, contents, config):
        self.calls += 1
        if self.calls == 1:
            call = SimpleNamespace(name="find_people", args={"query": "chief technology"})
            return SimpleNamespace(function_calls=[call], text=None,
                                   candidates=[SimpleNamespace(content=ask.types.Content(role="model", parts=[]))])
        found = contents[-1].parts[0].function_response.response["people"][0]
        return SimpleNamespace(function_calls=None, text=f"[[{found['id']}|{found['name']}]] leads it. [[x|Made Up]]")


def test_answer_runs_the_tool_loop(chart, monkeypatch):
    fake = FakeModels()
    monkeypatch.setattr(llm, "client", lambda: SimpleNamespace(models=fake))
    out = ask.answer("Who leads engineering?", chart, "strict")
    assert out["answer"] == "[[cto|Bo Chan]] leads it. Made Up"
    assert out["trail"] == [{"tool": "find_people", "args": {"query": "chief technology"}}]


def test_busy_models_raise_unavailable(chart, monkeypatch):
    class Busy:
        def generate_content(self, **_):
            raise ask.errors.APIError(503, {"error": {"message": "overloaded"}})

    monkeypatch.setattr(llm, "client", lambda: SimpleNamespace(models=Busy()))
    with pytest.raises(ask.Unavailable):
        ask.answer("Who leads engineering?", chart, "strict")
