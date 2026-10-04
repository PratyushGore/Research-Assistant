from unittest.mock import patch

from backend.agents.search.agent import (
    search_papers,
    _deduplicate_papers,
)
from backend.schemas.schemas import PaperMetadata


def test_empty_query():
    result = search_papers("")

    assert result.total_results == 0
    assert result.papers == []


def test_search_agent_returns_results():
    result = search_papers(
        "machine learning in healthcare",
        2,
    )

    assert result.total_results >= 0
    assert isinstance(result.papers, list)


def test_duplicate_papers_are_removed():

    paper1 = PaperMetadata(
        paper_id="arxiv:123",
        title="Machine Learning",
        authors=["Author A"],
        doi="10.1234/test",
    )

    paper2 = PaperMetadata(
        paper_id="s2:456",
        title="Machine Learning",
        authors=["Author A"],
        doi="10.1234/test",
    )

    result = _deduplicate_papers(
        [paper1, paper2]
    )

    assert len(result) == 1


@patch(
    "backend.agents.search.agent.search_semantic_scholar"
)
def test_semantic_scholar_failure(mock_search):

    mock_search.side_effect = Exception(
        "Semantic Scholar unavailable"
    )

    result = search_papers(
        "machine learning",
        2,
    )

    assert result is not None
    assert result.total_results >= 0