"""
Unit tests for multi-output parallel composer graph routing and fan-out.
"""

from pathlib import Path
import pytest

from backend.agents.output_renderer.renderer import render_output
from backend.orchestrator.graph import (
    _run_composer,
    build_pipeline_graph,
    composer_agent,
    composer_executive_summary,
    composer_literature_survey,
    composer_ppt,
    composer_research_paper,
    graph,
    guided_input_agent,
    qa_graph,
    route_to_composers,
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
    OutputType,
    PaperSummary,
    ProjectPresentationInfo,
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
# 4. Pipeline Fan-Out Execution Tests (Using node_overrides)
# ---------------------------------------------------------------------------

def test_pipeline_fan_out_multiple_outputs():
    """Graph executes parallel composer nodes and reduces composer_results."""
    findings, citations, guided_input = _make_dummy_findings_and_citations()

    # Create fake upstream nodes to avoid network / LLM calls
    fake_overrides = {
        "guided_input": lambda state: {},
        "search": lambda state: {},
        "ingestion": lambda state: {},
        "summarization": lambda state: {"findings": findings},
        "verification": lambda state: {},
        "citation": lambda state: {"citations": citations},
    }

    pipeline = build_pipeline_graph(node_overrides=fake_overrides)

    initial_state = {
        "request_id": "test-req-multi",
        "research_topic": "RAG Systems",
        "guided_input": guided_input,
        "selected_outputs": [OutputType.PPT, OutputType.RESEARCH_PAPER],
    }

    final_state = pipeline.invoke(initial_state)

    results = final_state.get("composer_results", [])
    assert len(results) == 2

    output_types_present = {r.output_type for r in results}
    assert output_types_present == {OutputType.PPT, OutputType.RESEARCH_PAPER}


def test_pipeline_fan_out_single_output():
    """Graph with single selected output produces exactly one composer result."""
    findings, citations, guided_input = _make_dummy_findings_and_citations()

    fake_overrides = {
        "guided_input": lambda state: {},
        "search": lambda state: {},
        "ingestion": lambda state: {},
        "summarization": lambda state: {"findings": findings},
        "verification": lambda state: {},
        "citation": lambda state: {"citations": citations},
    }

    pipeline = build_pipeline_graph(node_overrides=fake_overrides)

    initial_state = {
        "request_id": "test-req-single",
        "research_topic": "RAG Systems",
        "guided_input": guided_input,
        "selected_outputs": [OutputType.LITERATURE_SURVEY],
    }

    final_state = pipeline.invoke(initial_state)

    results = final_state.get("composer_results", [])
    assert len(results) == 1
    assert results[0].output_type == OutputType.LITERATURE_SURVEY


def test_compiled_graph_and_qa_graph_module_exports():
    """Ensure module-level graph and qa_graph exports are compiled LangGraph instances."""
    assert graph is not None
    assert qa_graph is not None
    assert hasattr(graph, "invoke")
    assert hasattr(qa_graph, "invoke")


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
