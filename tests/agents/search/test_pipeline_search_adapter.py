from backend.agents.search.agent import search_papers


def test_search_agent_accepts_research_topic():
    result = search_papers(
        "machine learning in healthcare",
        max_results_per_source=2,
    )

    assert result.query == "machine learning in healthcare"
    assert result.total_results >= 0
    assert isinstance(result.papers, list)