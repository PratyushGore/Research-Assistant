from backend.orchestrator.graph import PipelineState
from backend.agents.search.agent import search_papers
from backend.agents.ingestion.agent import ingest_and_store_pdf


def run_search_agent(state: PipelineState) -> PipelineState:
    """
    Adapter between LangGraph PipelineState
    and the Search Agent.
    """

    topic = state.get("research_topic")

    if not topic:
        raise ValueError(
            "Search Agent requires a research_topic."
        )

    print(
        f"[Pipeline Adapter] Searching for: {topic}"
    )

    search_result = search_papers(
        topic,
        max_results_per_source=8,
    )

    return {
        **state,
        "search_results": search_result,
    }


def run_ingestion_agent(state: PipelineState) -> PipelineState:
    """
    Adapter between LangGraph PipelineState
    and the Ingestion Agent.
    """

    search_results = state.get("search_results")

    if search_results is None:
        raise ValueError(
            "Ingestion Agent requires search_results."
        )

    ingestion_results = []

    for paper in search_results.papers:

        if not paper.url:
            print(
                f"[Pipeline Adapter] Skipping {paper.paper_id}: "
                "no PDF URL available."
            )
            continue

        print(
            f"[Pipeline Adapter] Ingesting: {paper.title}"
        )

        result = ingest_and_store_pdf(
            url=paper.url,
            metadata=paper,
        )

        ingestion_results.append(result)

    return {
        **state,
        "ingestion_results": ingestion_results,
    }