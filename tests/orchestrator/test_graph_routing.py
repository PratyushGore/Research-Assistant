"""
Unit tests for multi-output parallel composer graph routing and fan-out.
"""

from pathlib import Path
from unittest.mock import patch
import pytest

from backend.agents.output_renderer.renderer import render_output
from backend.orchestrator.graph import (
    _run_composer,
    build_compose_graph,
    build_pipeline_graph,
    build_research_graph,
    compose_graph,
    composer_agent,
    composer_executive_summary,
    composer_literature_survey,
    composer_ppt,
    composer_research_paper,
    graph,
    guided_input_agent,
    ingestion_agent,
    qa_graph,
    research_graph,
    route_to_composers,
    search_agent,
    should_continue_after_ingestion,
    should_continue_after_search,
)
from backend.schemas.schemas import (
    AcademicContentInfo,
    CitationResult,
    Claim,
    ComposerResult,
    CoverInfo,
    FindingsPacket,
    FormattedCitation,
    GuidedInputBundle,
    IngestionResult,
    OutputType,
    PaperMetadata,
    PaperSummary,
    PipelineStatus,
    ProjectPresentationInfo,
    SearchResult,
)


def _make_dummy_findings_and_citations():
    """Create lightweight in-memory findings and citation objects."""
    findings = FindingsPacket(
        topic="RAG Systems",
        summaries=[
            PaperSummary(
                paper_id="paper_1",
                summary="Study on RAG architectures.",
                key_findings=["RAG improves retrieval precision."],
                extracted_claims=[
                    Claim(
                        claim_id="c1",
                        text="RAG improves factuality",
                        source_paper_id="paper_1",
                    )
                ],
            )
        ],
        claims=[],
        contradictions=[],
    )
    citations = CitationResult(
        citation_style="APA",
        citations=[
            FormattedCitation(
                citation_id="cit_1",
                paper_id="paper_1",
                citation_style="APA",
                inline_marker="[1]",
                full_entry="Smith, J. (2024). RAG Architectures.",
            )
        ],
        bibliography=["Smith, J. (2024). RAG Architectures."],
    )
    guided_input = GuidedInputBundle(
        cover_info=CoverInfo(
            title="RAG Systems Research",
            authors=["Researcher"],
        ),
        project_presentation_info=ProjectPresentationInfo(
            problem_statement="Hallucinations in LLMs",
            tech_stack=["Python", "FAISS"],
            own_architecture_summary="Vector indexing and reranking",
            own_results_summary="90% precision",
        ),
        academic_content_info=AcademicContentInfo(
            methodology="Empirical evaluation on benchmark datasets.",
            dataset_or_sample="HotpotQA dataset",
            tools_used=["Python", "PyTorch"],
            what_was_measured="Exact Match and F1 score",
            key_results="18 point improvement in F1.",
        ),
    )
    return findings, citations, guided_input


# ---------------------------------------------------------------------------
# 1. Routing Function Tests
# ---------------------------------------------------------------------------

def test_route_to_composers_single_output():
    """Route with a single output returns a single composer node name."""
    state = {"selected_outputs": [OutputType.LITERATURE_SURVEY]}
    assert route_to_composers(state) == ["composer_literature_survey"]

    # String format
    state_str = {"selected_outputs": ["ppt"]}
    assert route_to_composers(state_str) == ["composer_ppt"]


def test_route_to_composers_multiple_outputs():
    """Route with multiple outputs returns corresponding composer nodes in order."""
    state = {
        "selected_outputs": [
            OutputType.PPT,
            OutputType.RESEARCH_PAPER,
        ]
    }
    assert route_to_composers(state) == [
        "composer_ppt",
        "composer_research_paper",
    ]

    # All four outputs in specific order
    all_outputs = [
        OutputType.EXECUTIVE_SUMMARY,
        OutputType.PPT,
        OutputType.LITERATURE_SURVEY,
        OutputType.RESEARCH_PAPER,
    ]
    state_all = {"selected_outputs": all_outputs}
    assert route_to_composers(state_all) == [
        "composer_executive_summary",
        "composer_ppt",
        "composer_literature_survey",
        "composer_research_paper",
    ]


def test_route_to_composers_duplicates():
    """Duplicates in selected_outputs are deduplicated while preserving order."""
    state = {
        "selected_outputs": [
            OutputType.PPT,
            OutputType.RESEARCH_PAPER,
            OutputType.PPT,
            "research_paper",
            OutputType.EXECUTIVE_SUMMARY,
        ]
    }
    assert route_to_composers(state) == [
        "composer_ppt",
        "composer_research_paper",
        "composer_executive_summary",
    ]


def test_route_to_composers_empty_and_missing_selection():
    """Missing or empty selected_outputs falls back to output_type or LITERATURE_SURVEY."""
    # Empty list falls back to default LITERATURE_SURVEY
    assert route_to_composers({"selected_outputs": []}) == [
        "composer_literature_survey"
    ]

    # Empty list falls back to specified output_type
    assert route_to_composers(
        {"selected_outputs": [], "output_type": OutputType.EXECUTIVE_SUMMARY}
    ) == ["composer_executive_summary"]

    # Missing selected_outputs falls back to default LITERATURE_SURVEY
    assert route_to_composers({}) == ["composer_literature_survey"]

    # Missing selected_outputs falls back to specified output_type
    assert route_to_composers({"output_type": OutputType.RESEARCH_PAPER}) == [
        "composer_research_paper"
    ]


# ---------------------------------------------------------------------------
# 2. Composer Helper Tests
# ---------------------------------------------------------------------------

def test_composer_helper_returns_only_delta():
    """_run_composer must return ONLY the composer_results delta, not the whole state."""
    findings, citations, guided_input = _make_dummy_findings_and_citations()

    state = {
        "request_id": "req-123",
        "research_topic": "RAG Systems",
        "findings": findings,
        "citations": citations,
        "guided_input": guided_input,
    }

    result_dict = _run_composer(state, OutputType.PPT)

    # Must contain ONLY composer_results
    assert list(result_dict.keys()) == ["composer_results"]
    assert len(result_dict["composer_results"]) == 1

    composer_result = result_dict["composer_results"][0]
    assert isinstance(composer_result, ComposerResult)
    assert composer_result.output_type == OutputType.PPT
    assert composer_result.title == "RAG Systems Research"

    # Must NOT have returned non-reducer keys like research_topic or guided_input
    assert "research_topic" not in result_dict
    assert "guided_input" not in result_dict
    assert "request_id" not in result_dict


def test_composer_helper_skips_when_missing_findings_or_citations():
    """_run_composer returns empty delta when findings or citations are missing."""
    state_no_findings = {"citations": CitationResult(citation_style="APA")}
    assert _run_composer(state_no_findings, OutputType.PPT) == {
        "composer_results": []
    }

    state_no_citations = {
        "findings": FindingsPacket(topic="Test", summaries=[], claims=[])
    }
    assert _run_composer(state_no_citations, OutputType.PPT) == {
        "composer_results": []
    }


def test_individual_composer_nodes():
    """Test the individual composer node functions."""
    findings, citations, guided_input = _make_dummy_findings_and_citations()
    state = {
        "findings": findings,
        "citations": citations,
        "guided_input": guided_input,
    }

    res_lit = composer_literature_survey(state)
    assert res_lit["composer_results"][0].output_type == OutputType.LITERATURE_SURVEY

    res_exec = composer_executive_summary(state)
    assert res_exec["composer_results"][0].output_type == OutputType.EXECUTIVE_SUMMARY

    res_ppt = composer_ppt(state)
    assert res_ppt["composer_results"][0].output_type == OutputType.PPT

    res_paper = composer_research_paper(state)
    assert res_paper["composer_results"][0].output_type == OutputType.RESEARCH_PAPER

    res_agent = composer_agent(state)
    assert len(res_agent["composer_results"]) == 1


# ---------------------------------------------------------------------------
# 3. Guided Input Pass-Through Test
# ---------------------------------------------------------------------------

def test_guided_input_agent_passthrough(capsys):
    """guided_input node prints a warning if missing and otherwise changes nothing."""
    # When missing: warning is printed, returns empty delta
    delta_missing = guided_input_agent({})
    assert delta_missing == {}
    captured = capsys.readouterr()
    assert "Warning" in captured.out

    # When present: no warning printed, returns empty delta
    _, _, guided_input = _make_dummy_findings_and_citations()
    delta_present = guided_input_agent({"guided_input": guided_input})
    assert delta_present == {}
    captured2 = capsys.readouterr()
    assert "Warning" not in captured2.out


# ---------------------------------------------------------------------------
# 4. Compose Graph Fan-Out Execution Tests
# ---------------------------------------------------------------------------

def test_compose_graph_fan_out_multiple_outputs():
    """compose_graph executes parallel composer nodes from pre-populated findings and citations."""
    findings, citations, guided_input = _make_dummy_findings_and_citations()

    pipeline = build_compose_graph()

    initial_state = {
        "request_id": "test-req-multi",
        "research_topic": "RAG Systems",
        "findings": findings,
        "citations": citations,
        "guided_input": guided_input,
        "selected_outputs": [OutputType.PPT, OutputType.RESEARCH_PAPER],
    }

    final_state = pipeline.invoke(initial_state)

    results = final_state.get("composer_results", [])
    assert len(results) == 2

    output_types_present = {r.output_type for r in results}
    assert output_types_present == {OutputType.PPT, OutputType.RESEARCH_PAPER}


def test_compose_graph_fan_out_single_output():
    """compose_graph with single selected output produces exactly one composer result."""
    findings, citations, guided_input = _make_dummy_findings_and_citations()

    pipeline = build_compose_graph()

    initial_state = {
        "request_id": "test-req-single",
        "research_topic": "RAG Systems",
        "findings": findings,
        "citations": citations,
        "guided_input": guided_input,
        "selected_outputs": [OutputType.LITERATURE_SURVEY],
    }

    final_state = pipeline.invoke(initial_state)

    results = final_state.get("composer_results", [])
    assert len(results) == 1
    assert results[0].output_type == OutputType.LITERATURE_SURVEY


def test_compiled_graph_and_qa_graph_module_exports():
    """Ensure module-level graph, qa_graph, research_graph, and compose_graph exports are compiled LangGraph instances."""
    assert graph is not None
    assert qa_graph is not None
    assert research_graph is not None
    assert compose_graph is not None
    assert hasattr(graph, "invoke")
    assert hasattr(qa_graph, "invoke")
    assert hasattr(research_graph, "invoke")
    assert hasattr(compose_graph, "invoke")


# ---------------------------------------------------------------------------
# 5. Output File Path Collision Test
# ---------------------------------------------------------------------------

def test_parallel_output_render_paths_dont_collide(tmp_path: Path):
    """
    Verify that two outputs generated in parallel don't write to the same file path.
    Tests rendering PPT (.pptx) and Research Paper (.docx) to disk.
    """
    findings, citations, guided_input = _make_dummy_findings_and_citations()

    ppt_delta = _run_composer(
        {"findings": findings, "citations": citations, "guided_input": guided_input},
        OutputType.PPT,
    )
    paper_delta = _run_composer(
        {"findings": findings, "citations": citations, "guided_input": guided_input},
        OutputType.RESEARCH_PAPER,
    )

    ppt_result = ppt_delta["composer_results"][0]
    paper_result = paper_delta["composer_results"][0]

    ppt_path = tmp_path / "deliverable.pptx"
    paper_path = tmp_path / "deliverable.docx"

    # Paths must be distinct
    assert ppt_path != paper_path

    # Render both outputs
    rendered_ppt = render_output(ppt_result, "pptx", ppt_path)
    rendered_paper = render_output(paper_result, "docx", paper_path)

    # Both files must exist independently and have non-zero size
    assert rendered_ppt.exists()
    assert rendered_ppt.stat().st_size > 0

    assert rendered_paper.exists()
    assert rendered_paper.stat().st_size > 0


# ---------------------------------------------------------------------------
# 6. Failure Router Unit Tests
# ---------------------------------------------------------------------------

def test_should_continue_after_search_router():
    """should_continue_after_search returns 'stop' when failed, else 'continue'."""
    # Failed status returns 'stop'
    failed_state = {
        "pipeline_status": PipelineStatus(
            stage="failed",
            detail="No papers found for this topic.",
        )
    }
    assert should_continue_after_search(failed_state) == "stop"

    # Dict format support
    dict_failed = {"pipeline_status": {"stage": "failed", "detail": "error"}}
    assert should_continue_after_search(dict_failed) == "stop"

    # Missing status returns 'continue'
    assert should_continue_after_search({}) == "continue"

    # Non-failed status returns 'continue'
    non_failed = {"pipeline_status": PipelineStatus(stage="in_progress")}
    assert should_continue_after_search(non_failed) == "continue"


def test_should_continue_after_ingestion_router():
    """should_continue_after_ingestion returns 'stop' when failed, else 'continue'."""
    # Failed status returns 'stop'
    failed_state = {
        "pipeline_status": PipelineStatus(
            stage="failed",
            detail="All papers failed during ingestion.",
        )
    }
    assert should_continue_after_ingestion(failed_state) == "stop"

    # Dict format support
    dict_failed = {"pipeline_status": {"stage": "failed"}}
    assert should_continue_after_ingestion(dict_failed) == "stop"

    # Missing status returns 'continue'
    assert should_continue_after_ingestion({}) == "continue"

    # Non-failed status returns 'continue'
    non_failed = {"pipeline_status": PipelineStatus(stage="in_progress")}
    assert should_continue_after_ingestion(non_failed) == "continue"


# ---------------------------------------------------------------------------
# 7. Search and Ingestion Node Failure Logic Tests
# ---------------------------------------------------------------------------

def test_search_agent_zero_results_sets_failure_status():
    """search_agent sets pipeline_status stage='failed' when search returns 0 papers."""
    empty_result = SearchResult(query="obscure topic", papers=[], total_results=0)

    with patch("backend.agents.search.agent.search_papers", return_value=empty_result):
        state = {"research_topic": "obscure topic"}
        new_state = search_agent(state)

    status = new_state.get("pipeline_status")
    assert status is not None
    assert status.stage == "failed"
    assert status.detail == "No papers found for this topic."


def test_ingestion_agent_empty_search_results_sets_failure_status():
    """ingestion_agent sets pipeline_status with 'No papers to ingest.' when papers list is empty."""
    empty_search = SearchResult(query="topic", papers=[], total_results=0)
    state = {"search_results": empty_search}

    new_state = ingestion_agent(state)

    status = new_state.get("pipeline_status")
    assert status is not None
    assert status.stage == "failed"
    assert status.detail == "No papers to ingest."
    assert new_state.get("ingestion_results") == []


def test_ingestion_agent_all_papers_fail_sets_distinct_detail():
    """ingestion_agent distinguishes 'All papers failed during ingestion.' when papers exist but fail."""
    paper = PaperMetadata(
        paper_id="paper_fail_1",
        title="Failing Paper",
        url="http://example.com/fail.pdf",
    )
    search_with_paper = SearchResult(query="topic", papers=[paper], total_results=1)

    # Ingestion failure returns an IngestionResult with empty chunks and raw_text None
    failed_ingest = IngestionResult(
        paper_id="paper_fail_1",
        metadata=paper,
        chunks=[],
        raw_text=None,
    )

    with patch(
        "backend.agents.ingestion.agent.ingest_and_store_pdf",
        return_value=failed_ingest,
    ):
        state = {"search_results": search_with_paper}
        new_state = ingestion_agent(state)

    status = new_state.get("pipeline_status")
    assert status is not None
    assert status.stage == "failed"
    assert status.detail == "All papers failed during ingestion."
    assert new_state.get("ingestion_results") == []


# ---------------------------------------------------------------------------
# 8. Graph Execution Failure Routing Tests (Using node_overrides)
# ---------------------------------------------------------------------------

def test_graph_zero_search_results_stops_before_ingestion():
    """
    A topic that returns zero search results reaches END with pipeline_status.stage == 'failed'
    and never calls ingestion or summarization in research_graph.
    """
    calls = {"ingestion": 0, "summarization": 0}

    def spy_ingestion(state):
        calls["ingestion"] += 1
        return {}

    def spy_summarization(state):
        calls["summarization"] += 1
        return {}

    fake_overrides = {
        "search": lambda state: {
            "search_results": SearchResult(query="empty topic", papers=[], total_results=0),
            "pipeline_status": PipelineStatus(
                stage="failed",
                detail="No papers found for this topic.",
            ),
        },
        "ingestion": spy_ingestion,
        "summarization": spy_summarization,
    }

    pipeline = build_research_graph(node_overrides=fake_overrides)

    initial_state = {
        "request_id": "req-zero-search",
        "research_topic": "empty topic",
    }

    final_state = pipeline.invoke(initial_state)

    # Pipeline stopped at END after search router
    assert final_state.get("pipeline_status") is not None
    assert final_state["pipeline_status"].stage == "failed"
    assert final_state["pipeline_status"].detail == "No papers found for this topic."

    # Downstream nodes were NEVER called
    assert calls["ingestion"] == 0
    assert calls["summarization"] == 0
    assert final_state.get("composer_results", []) == []


def test_graph_all_ingestion_failing_stops_before_summarization():
    """
    A topic where search finds papers but every PDF download fails reaches END
    at the ingestion failure point with a distinct detail message and never calls summarization.
    """
    calls = {"summarization": 0, "verification": 0}

    def spy_summarization(state):
        calls["summarization"] += 1
        return {}

    def spy_verification(state):
        calls["verification"] += 1
        return {}

    paper = PaperMetadata(
        paper_id="paper_1",
        title="Found Paper",
        url="http://example.com/paper.pdf",
    )

    fake_overrides = {
        "search": lambda state: {
            "search_results": SearchResult(query="topic", papers=[paper], total_results=1),
        },
        "ingestion": lambda state: {
            "ingestion_results": [],
            "pipeline_status": PipelineStatus(
                stage="failed",
                detail="All papers failed during ingestion.",
            ),
        },
        "summarization": spy_summarization,
        "verification": spy_verification,
    }

    pipeline = build_research_graph(node_overrides=fake_overrides)

    initial_state = {
        "request_id": "req-ingestion-fail",
        "research_topic": "topic",
    }

    final_state = pipeline.invoke(initial_state)

    # Pipeline stopped at END after ingestion router
    assert final_state.get("pipeline_status") is not None
    assert final_state["pipeline_status"].stage == "failed"
    assert final_state["pipeline_status"].detail == "All papers failed during ingestion."

    # Downstream nodes were NEVER called
    assert calls["summarization"] == 0
    assert calls["verification"] == 0
    assert final_state.get("composer_results", []) == []


def test_research_graph_normal_success_path():
    """
    Normal success path in research_graph runs through search -> ingestion -> summarization ->
    verification -> citation -> END, populating findings and citations without touching composer.
    """
    findings, citations, _ = _make_dummy_findings_and_citations()
    paper = PaperMetadata(paper_id="paper_1", title="RAG Architectures")

    calls = {"ingestion": 0, "summarization": 0, "verification": 0, "citation": 0}

    def spy_ingestion(state):
        calls["ingestion"] += 1
        return {
            "ingestion_results": [
                IngestionResult(
                    paper_id="paper_1",
                    metadata=paper,
                    chunks=[],
                )
            ]
        }

    def spy_summarization(state):
        calls["summarization"] += 1
        return {"findings": findings}

    def spy_verification(state):
        calls["verification"] += 1
        return {}

    def spy_citation(state):
        calls["citation"] += 1
        return {"citations": citations}

    fake_overrides = {
        "search": lambda state: {
            "search_results": SearchResult(query="RAG", papers=[paper], total_results=1),
        },
        "ingestion": spy_ingestion,
        "summarization": spy_summarization,
        "verification": spy_verification,
        "citation": spy_citation,
    }

    pipeline = build_research_graph(node_overrides=fake_overrides)

    initial_state = {
        "request_id": "req-success-path",
        "research_topic": "RAG",
    }

    final_state = pipeline.invoke(initial_state)

    # All research linear nodes were executed in sequence
    assert calls["ingestion"] == 1
    assert calls["summarization"] == 1
    assert calls["verification"] == 1
    assert calls["citation"] == 1

    assert final_state.get("findings") == findings
    assert final_state.get("citations") == citations
    assert final_state.get("composer_results", []) == []


def test_sequential_research_and_compose_graph_invocation():
    """
    End-to-end integration: research_graph runs first producing findings/citations,
    then compose_graph reuses those findings to produce deliverables without re-running search.
    """
    findings, citations, guided_input = _make_dummy_findings_and_citations()
    paper = PaperMetadata(paper_id="paper_1", title="RAG Architectures")

    search_calls = 0

    def mock_search(state):
        nonlocal search_calls
        search_calls += 1
        return {
            "search_results": SearchResult(query="RAG", papers=[paper], total_results=1)
        }

    research_overrides = {
        "search": mock_search,
        "ingestion": lambda s: {
            "ingestion_results": [IngestionResult(paper_id="paper_1", metadata=paper, chunks=[])]
        },
        "summarization": lambda s: {"findings": findings},
        "verification": lambda s: {},
        "citation": lambda s: {"citations": citations},
    }

    research_pipe = build_research_graph(node_overrides=research_overrides)
    compose_pipe = build_compose_graph()

    # Step 1: Run research
    research_state = research_pipe.invoke({
        "request_id": "r1",
        "research_topic": "RAG",
    })

    assert research_state.get("findings") is not None
    assert research_state.get("citations") is not None
    assert research_state.get("composer_results", []) == []
    assert search_calls == 1

    # Step 2: Later, run compose using research output
    compose_state = compose_pipe.invoke({
        **research_state,
        "guided_input": guided_input,
        "selected_outputs": [OutputType.PPT],
    })

    # Search was NOT called again
    assert search_calls == 1
    composer_results = compose_state.get("composer_results", [])
    assert len(composer_results) == 1
    assert composer_results[0].output_type == OutputType.PPT


def test_backward_compatible_pipeline_graph():
    """
    Verify existing build_pipeline_graph still functions end-to-end as before.
    """
    findings, citations, guided_input = _make_dummy_findings_and_citations()
    paper = PaperMetadata(paper_id="paper_1", title="RAG Architectures")

    fake_overrides = {
        "guided_input": lambda state: {},
        "search": lambda state: {
            "search_results": SearchResult(query="RAG", papers=[paper], total_results=1),
        },
        "ingestion": lambda s: {
            "ingestion_results": [IngestionResult(paper_id="paper_1", metadata=paper, chunks=[])]
        },
        "summarization": lambda state: {"findings": findings},
        "verification": lambda state: {},
        "citation": lambda state: {"citations": citations},
    }

    pipeline = build_pipeline_graph(node_overrides=fake_overrides)

    initial_state = {
        "request_id": "req-legacy-path",
        "research_topic": "RAG",
        "guided_input": guided_input,
        "selected_outputs": [OutputType.LITERATURE_SURVEY],
    }

    final_state = pipeline.invoke(initial_state)
    composer_results = final_state.get("composer_results", [])
    assert len(composer_results) == 1
    assert composer_results[0].output_type == OutputType.LITERATURE_SURVEY


# ---------------------------------------------------------------------------
# 11. Compose Graph File Rendering Tests (Phase 4c-i)
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("output_type,expected_ext", [
    (OutputType.LITERATURE_SURVEY, "docx"),
    (OutputType.EXECUTIVE_SUMMARY, "docx"),
    (OutputType.RESEARCH_PAPER, "docx"),
    (OutputType.PPT, "pptx"),
])
def test_compose_graph_renders_real_file_on_disk(output_type, expected_ext):
    """Confirm a real file exists on disk under backend/generated_outputs/ after compose_graph.invoke."""
    findings, citations, guided_input = _make_dummy_findings_and_citations()
    req_id = f"test-render-{output_type.value}"

    state = {
        "request_id": req_id,
        "research_topic": "AI Research",
        "findings": findings,
        "citations": citations,
        "guided_input": guided_input,
        "selected_outputs": [output_type],
    }

    final_state = compose_graph.invoke(state)

    results = final_state.get("composer_results", [])
    assert len(results) == 1
    composer_result = results[0]
    assert composer_result.output_type == output_type
    assert composer_result.file_path is not None

    file_path = Path(composer_result.file_path)
    assert file_path.exists(), f"Expected rendered file to exist at {file_path}"
    assert file_path.is_file()
    assert file_path.stat().st_size > 0
    assert file_path.suffix == f".{expected_ext}"
    assert "generated_outputs" in file_path.parts
    assert req_id in file_path.parts
    assert file_path.name == f"{output_type.value}.{expected_ext}"


def test_compose_graph_fan_out_multiple_outputs_renders_all_files():
    """compose_graph fan-out renders all selected outputs to disk with populated file_path."""
    findings, citations, guided_input = _make_dummy_findings_and_citations()
    req_id = "test-render-all-outputs"

    selected = [
        OutputType.LITERATURE_SURVEY,
        OutputType.EXECUTIVE_SUMMARY,
        OutputType.PPT,
        OutputType.RESEARCH_PAPER,
    ]

    state = {
        "request_id": req_id,
        "research_topic": "AI Research All",
        "findings": findings,
        "citations": citations,
        "guided_input": guided_input,
        "selected_outputs": selected,
    }

    final_state = compose_graph.invoke(state)

    results = final_state.get("composer_results", [])
    assert len(results) == 4

    for r in results:
        assert r.file_path is not None
        p = Path(r.file_path)
        assert p.exists()
        assert p.stat().st_size > 0
        if r.output_type == OutputType.PPT:
            assert p.suffix == ".pptx"
        else:
            assert p.suffix == ".docx"


def test_render_failure_sets_file_path_none_without_crashing_fan_out():
    """If rendering fails for an output, log warning and set file_path=None without crashing fan-out."""
    findings, citations, guided_input = _make_dummy_findings_and_citations()

    state = {
        "request_id": "test-render-failure",
        "research_topic": "Failure Resilience",
        "findings": findings,
        "citations": citations,
        "guided_input": guided_input,
        "selected_outputs": [OutputType.PPT, OutputType.LITERATURE_SURVEY],
    }

    with patch("backend.agents.output_renderer.renderer.render_output", side_effect=RuntimeError("Disk I/O error")):
        final_state = compose_graph.invoke(state)

    results = final_state.get("composer_results", [])
    assert len(results) == 2
    for r in results:
        assert r.file_path is None

