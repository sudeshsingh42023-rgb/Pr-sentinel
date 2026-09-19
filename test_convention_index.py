from pr_sentinel.agents.convention_agent import ConventionIndex


def test_search_finds_relevant_snippet():
    idx = ConventionIndex([
        {"path": "a.py", "text": "def validate_email(addr): return '@' in addr"},
        {"path": "b.py", "text": "class Widget: pass"},
    ])
    results = idx.search("email validation function", top_k=1)
    assert results[0]["path"] == "a.py"


def test_empty_index_returns_nothing():
    idx = ConventionIndex([])
    assert idx.search("anything") == []
