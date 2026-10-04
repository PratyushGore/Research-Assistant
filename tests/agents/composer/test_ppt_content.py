import logging
import pytest

from backend.agents.composer.ppt_content import (
    CHART_FIGURE_ID,
    DIAGRAM_FIGURE_ID,
    build_evidence_pack,
    build_ppt_structured,
    compute_chart_figure,
    compute_chart_figure_and_notes,
    build_table_slide,
    build_references_slides,
    build_contradictions_slide,
    build_deterministic_fallback_deck,
    extract_paper_metadata_from_citation,
    sanitize_text,
    sanitize_slide,
    validate_diagram_nodes_and_edges,
)
from backend.agents.composer.agent import ComposerAgent
from backend.schemas.schemas import (
    Claim,
    ContradictionDetail,
    CoverInfo,
    FindingsPacket,
    FormattedCitation,
    GuidedInputBundle,
    OutputType,
    PaperSummary,
    ProjectPresentationInfo,
    CitationResult,
    SlideSpec,
)


class FakeLLM:
    """Mock LLM client returning predetermined strings or raising exceptions."""

    def __init__(self, response_text: str = "", exception: Exception | None = None):
        self.response_text = response_text
        self.exception = exception
        self.call_count = 0
        self.last_prompt = ""

    def generate(
        self,
        prompt: str,
        *,
        paper_id: str,
        agent_name: str,
        purpose: str,
        use_cache: bool = True,
    ) -> str:
        self.call_count += 1
        self.last_prompt = prompt
        if self.exception:
            raise self.exception
        return self.response_text


def sample_inputs():
    guided_input = GuidedInputBundle(
        cover_info=CoverInfo(
            title="Multi-Agent Literature Assistant",
            subtitle="Architectural Evaluation and Benchmarks",
        ),
        project_presentation_info=ProjectPresentationInfo(
            problem_statement="Manual literature research is inefficient and prone to hallucinated citations.",
            tech_stack=["Python", "LangGraph", "ChromaDB"],
            own_architecture_summary="FastAPI service dispatches research tasks to LangGraph workflow with vector search.",
            own_results_summary="System achieves 35 percent speedup and zero hallucination citations on benchmark sets.",
        ),
    )

    claims = [
        Claim(
            claim_id="claim_01",
            text="Decoupled multi-agent systems reduce latency by 35%.",
            source_paper_id="paper_1",
            verification_status="verified",
        ),
        Claim(
            claim_id="claim_02",
            text="Vector databases improve recall for dense retrieval.",
            source_paper_id="paper_2",
            verification_status="verified",
        ),
        Claim(
            claim_id="claim_03",
            text="Unverified claim about quantum computing.",
            source_paper_id="paper_1",
            verification_status="unverified",
        ),
        Claim(
            claim_id="claim_04",
            text="Pending claim about robotics.",
            source_paper_id="paper_2",
            verification_status="pending",
        ),
    ]

    findings = FindingsPacket(
        topic="Multi-Agent AI Literature Systems",
        summaries=[
            PaperSummary(
                paper_id="paper_1",
                title="Multi-Agent Scalability",
                authors=["Vaswani, A.", "Jones, B."],
                year=2021,
                venue="Journal of AI",
                summary="Study on multi-agent execution efficiency.",
            ),
            PaperSummary(
                paper_id="paper_2",
                title="Dense Retrieval at Scale",
                authors=["Smith, J.", "Doe, B."],
                year=2022,
                venue="IEEE Trans.",
                summary="Study on dense retrieval systems.",
            ),
        ],
        claims=claims,
    )

    citations = CitationResult(
        citation_style="apa",
        citations=[
            FormattedCitation(
                citation_id="cit_1",
                paper_id="paper_1",
                citation_style="apa",
                inline_marker="[1]",
                full_entry="Vaswani, A. et al. (2021). Multi-Agent Scalability. Journal of AI.",
            ),
            FormattedCitation(
                citation_id="cit_2",
                paper_id="paper_2",
                citation_style="apa",
                inline_marker="[2]",
                full_entry="J. Smith and B. Doe (2022). Dense Retrieval at Scale. IEEE Trans.",
            ),
        ],
    )

    return guided_input, findings, citations


class TestPPTContentLayer:
    def test_citation_metadata_extraction(self):
        cit_apa = FormattedCitation(
            citation_id="c1",
            paper_id="p1",
            citation_style="apa",
            inline_marker="(Konade, 2023)",
            full_entry="Konade, S. (2023). Multi-Agent Research Workflows. AI Review.",
        )
        title, year = extract_paper_metadata_from_citation(cit_apa)
        assert title == "Multi-Agent Research Workflows"
        assert year == 2023

        cit_ieee = FormattedCitation(
            citation_id="c2",
            paper_id="p2",
            citation_style="ieee",
            inline_marker="[2]",
            full_entry="J. Doe, \"Advances in Graph Neural Networks,\" NeurIPS, 2022. doi: 10.1234",
        )
        title_ieee, year_ieee = extract_paper_metadata_from_citation(cit_ieee)
        assert title_ieee == "Advances in Graph Neural Networks"
        assert year_ieee == 2022

    def test_evidence_pack_counts_and_filters_unverified(self):
        _, findings, citations = sample_inputs()
        pack = build_evidence_pack(findings, citations)

        assert len(pack.verified_claims) == 2
        assert "claim_01" in pack.verified_claim_ids
        assert "claim_02" in pack.verified_claim_ids
        assert "claim_03" not in pack.verified_claim_ids
        assert "claim_04" not in pack.verified_claim_ids

        assert pack.claim_counts["verified"] == 2
        assert pack.claim_counts["unverified"] == 1
        assert pack.claim_counts["pending"] == 1

        assert pack.claims_per_paper["paper_1"] == 1
        assert pack.claims_per_paper["paper_2"] == 1

        assert pack.papers_per_year == {"2021": 1, "2022": 1}
        assert pack.distinct_years == {2021, 2022}

    def test_valid_json_produces_expected_slide_layouts(self):
        guided_input, findings, citations = sample_inputs()

        valid_json = """
        {
          "slides": [
            {
              "layout": "title",
              "title": "Multi-Agent Literature Assistant",
              "bullets": ["Architectural Evaluation and Benchmarks"],
              "notes": "Title notes"
            },
            {
              "layout": "agenda",
              "title": "Agenda",
              "bullets": ["Introduction", "Problem", "Literature", "Architecture", "Conclusion"],
              "notes": "Agenda notes"
            },
            {
              "layout": "bullets",
              "title": "Problem Statement",
              "bullets": ["Literature search is slow.", "Hallucinations degrade trust."],
              "notes": "Problem notes"
            },
            {
              "layout": "bullets",
              "title": "Literature Findings",
              "bullets": ["Decoupled multi-agent systems reduce latency by 35%"],
              "claim_ids": ["claim_01"],
              "notes": "Literature notes"
            },
            {
              "layout": "chart",
              "title": "Publication Trends",
              "figure_id": "fig_chart_1",
              "notes": "Chart notes"
            },
            {
              "layout": "table",
              "title": "Literature Comparison",
              "table_header": ["Paper", "Key Finding", "Status"],
              "table_rows": [["(Vaswani, 2021)", "Latency reduction", "Verified"]],
              "notes": "Table notes"
            },
            {
              "layout": "diagram",
              "title": "System Architecture",
              "figure_id": "fig_diagram_1",
              "notes": "Diagram notes"
            },
            {
              "layout": "bullets",
              "title": "Own Results",
              "bullets": ["35 percent speedup demonstrated.", "Zero hallucinated citations."],
              "notes": "Results notes"
            },
            {
              "layout": "bullets",
              "title": "Comparison with Literature",
              "bullets": ["Vector databases improve recall for dense retrieval."],
              "claim_ids": ["claim_02"],
              "notes": "Comparison notes"
            },
            {
              "layout": "closing",
              "title": "Conclusion",
              "bullets": ["Q&A"],
              "notes": "Closing notes"
            }
          ],
          "diagram_nodes": ["FastAPI service", "LangGraph workflow", "vector search"],
          "diagram_edges": [["FastAPI service", "LangGraph workflow"], ["LangGraph workflow", "vector search"]]
        }
        """

        mock_llm = FakeLLM(response_text=valid_json)
        structured = build_ppt_structured(guided_input, findings, citations, llm=mock_llm)

        assert mock_llm.call_count == 1
        assert len(structured.slides) >= 10

        layouts = [s.layout for s in structured.slides]
        assert "title" in layouts
        assert "agenda" in layouts
        assert "chart" in layouts
        assert "table" in layouts
        assert "diagram" in layouts
        assert "closing" in layouts

        # Assert speaker notes are populated and non-empty for all slides
        for slide in structured.slides:
            assert slide.notes is not None and len(slide.notes) > 0

    def test_unverified_and_unknown_claim_ids_dropped(self):
        guided_input, findings, citations = sample_inputs()

        json_with_bad_claims = """
        {
          "slides": [
            {
              "layout": "title",
              "title": "Test Title",
              "bullets": ["Sub"]
            },
            {
              "layout": "bullets",
              "title": "Literature Findings",
              "bullets": [
                "Valid claim [claim_01]",
                "Unverified claim [claim_03]",
                "Unknown claim [claim_fake_99]"
              ],
              "claim_ids": ["claim_01", "claim_03", "claim_fake_99"]
            }
          ],
          "diagram_nodes": ["FastAPI", "LangGraph"],
          "diagram_edges": []
        }
        """

        mock_llm = FakeLLM(response_text=json_with_bad_claims)
        structured = build_ppt_structured(guided_input, findings, citations, llm=mock_llm)

        lit_slide = next(s for s in structured.slides if "Literature" in s.title)
        # claim_03 (unverified) and claim_fake_99 (nonexistent) must be dropped
        assert "claim_03" not in lit_slide.claim_ids
        assert "claim_fake_99" not in lit_slide.claim_ids
        assert "claim_01" in lit_slide.claim_ids

        # Unverified and unknown claim bullets were dropped
        assert len(lit_slide.bullets) == 1
        assert "claim_01" not in lit_slide.bullets[0]
        assert "[1]" in lit_slide.bullets[0]

    def test_bullets_exceeding_five_truncated(self):
        guided_input, findings, citations = sample_inputs()

        json_too_many_bullets = """
        {
          "slides": [
            {
              "layout": "title",
              "title": "Title",
              "bullets": ["B1", "B2", "B3", "B4", "B5", "B6", "B7", "B8"]
            },
            {
              "layout": "agenda",
              "title": "Agenda",
              "bullets": ["1", "2", "3", "4", "5", "6"]
            }
          ]
        }
        """

        mock_llm = FakeLLM(response_text=json_too_many_bullets)
        structured = build_ppt_structured(guided_input, findings, citations, llm=mock_llm)

        for slide in structured.slides:
            assert len(slide.bullets) <= 5

    def test_invalid_json_triggers_deterministic_fallback(self, caplog):
        guided_input, findings, citations = sample_inputs()

        mock_llm = FakeLLM(response_text="Not valid json { [broken")
        with caplog.at_level(logging.WARNING):
            structured = build_ppt_structured(guided_input, findings, citations, llm=mock_llm)

        assert len(structured.slides) >= 9
        assert any("Falling back to deterministic structured deck" in r.message for r in caplog.records)
        assert structured.figures[0].figure_id == CHART_FIGURE_ID
        assert structured.figures[1].figure_id == DIAGRAM_FIGURE_ID

    def test_llm_exception_triggers_deterministic_fallback(self, caplog):
        guided_input, findings, citations = sample_inputs()

        mock_llm = FakeLLM(exception=RuntimeError("Google Gemini API error: 429 ResourceExhausted"))
        with caplog.at_level(logging.WARNING):
            structured = build_ppt_structured(guided_input, findings, citations, llm=mock_llm)

        assert len(structured.slides) >= 9
        assert any("429 ResourceExhausted" in r.message for r in caplog.records)

    def test_diagram_nodes_not_in_user_text_are_removed(self):
        user_text = "FastAPI service dispatches research tasks to LangGraph workflow with vector search."

        raw_nodes = [
            "FastAPI service",        # Valid (in user text)
            "LangGraph workflow",     # Valid (in user text)
            "vector search",          # Valid (in user text)
            "Kubernetes cluster",     # INVALID: words not in user text
            "Redis cache layer",      # INVALID: words not in user text
            "Very long component label with six words in it", # INVALID: > 3 words
        ]
        raw_edges = [
            ["FastAPI service", "LangGraph workflow"],
            ["LangGraph workflow", "Kubernetes cluster"],
            ["Kubernetes cluster", "vector search"],
        ]

        valid_nodes, valid_edges = validate_diagram_nodes_and_edges(
            raw_nodes, raw_edges, user_text
        )

        assert "FastAPI service" in valid_nodes
        assert "LangGraph workflow" in valid_nodes
        assert "vector search" in valid_nodes
        assert "Kubernetes cluster" not in valid_nodes
        assert "Redis cache layer" not in valid_nodes
        assert "Very long component label with six words in it" not in valid_nodes

        # Edges touching dropped nodes must also be removed
        assert ("FastAPI service", "LangGraph workflow") in valid_edges
        assert ("LangGraph workflow", "Kubernetes cluster") not in valid_edges
        assert ("Kubernetes cluster", "vector search") not in valid_edges

    def test_chart_figure_values_equal_computed_counts(self):
        guided_input, findings, citations = sample_inputs()
        evidence_pack = build_evidence_pack(findings, citations)

        # 2 distinct years: uses claims_per_source
        chart_fig = compute_chart_figure(evidence_pack)
        assert chart_fig.data_source == "claims_per_source"
        assert chart_fig.labels == ["[1]", "[2]"]
        assert chart_fig.values == [1.0, 1.0]

        # 4 distinct years: uses papers_per_year
        citations_4_years = CitationResult(
            citation_style="apa",
            citations=[
                FormattedCitation(citation_id="c1", paper_id="p1", citation_style="apa", inline_marker="[1]", full_entry="Author A (2019). Title A."),
                FormattedCitation(citation_id="c2", paper_id="p2", citation_style="apa", inline_marker="[2]", full_entry="Author B (2020). Title B."),
                FormattedCitation(citation_id="c3", paper_id="p3", citation_style="apa", inline_marker="[3]", full_entry="Author C (2021). Title C."),
                FormattedCitation(citation_id="c4", paper_id="p4", citation_style="apa", inline_marker="[4]", full_entry="Author D (2022). Title D."),
            ],
        )
        findings_4_years = FindingsPacket(
            topic="Temporal Topic",
            summaries=[
                PaperSummary(paper_id="p1", title="Title A", year=2019, summary="Sum A"),
                PaperSummary(paper_id="p2", title="Title B", year=2020, summary="Sum B"),
                PaperSummary(paper_id="p3", title="Title C", year=2021, summary="Sum C"),
                PaperSummary(paper_id="p4", title="Title D", year=2022, summary="Sum D"),
            ],
            claims=[
                Claim(claim_id="cl1", text="C1", source_paper_id="p1", verification_status="verified"),
                Claim(claim_id="cl2", text="C2", source_paper_id="p2", verification_status="verified"),
                Claim(claim_id="cl3", text="C3", source_paper_id="p3", verification_status="verified"),
                Claim(claim_id="cl4", text="C4", source_paper_id="p4", verification_status="verified"),
            ],
        )
        pack_4_years = build_evidence_pack(findings_4_years, citations_4_years)
        chart_4 = compute_chart_figure(pack_4_years)
        assert chart_4.data_source == "papers_per_year"
        assert chart_4.labels == ["2019", "2020", "2021", "2022"]
        assert chart_4.values == [1.0, 1.0, 1.0, 1.0]

    def test_composer_agent_ppt_integration(self):
        guided_input, findings, citations = sample_inputs()

        valid_json = """
        {
          "slides": [
            {"layout": "title", "title": "Integrated Deck", "bullets": ["Sub"]}
          ],
          "diagram_nodes": ["FastAPI", "LangGraph"],
          "diagram_edges": []
        }
        """
        mock_llm = FakeLLM(response_text=valid_json)
        agent = ComposerAgent(llm=mock_llm)

        result_ppt = agent.compose(OutputType.PPT, guided_input, findings, citations)
        assert result_ppt.output_type == OutputType.PPT
        assert result_ppt.structured is not None
        assert len(result_ppt.structured.slides) >= 1
        assert "## Title" in result_ppt.content
        assert "## Problem" in result_ppt.content
        assert "Problem" in result_ppt.sections

        result_survey = agent.compose(OutputType.LITERATURE_SURVEY, guided_input, findings, citations)
        assert result_survey.output_type == OutputType.LITERATURE_SURVEY
        assert result_survey.structured is not None

    # -----------------------------------------------------------------------
    # Requirement K Targeted Tests
    # -----------------------------------------------------------------------

    def test_sanitizer_raw_ids_and_unknown_papers(self):
        """Test raw-ID sanitizer cases, mixed lists, and unknown paper removal."""
        _, findings, citations = sample_inputs()
        evidence_pack = build_evidence_pack(findings, citations)

        # 1. Direct raw claim ID with arxiv ID
        raw_text_1 = "Results shown in [arxiv:1905.09130v1:claim:4] prove scaling."
        # Map arxiv id as paper_2
        evidence_pack.paper_number_map["arxiv:1905.09130v1"] = 2
        sanitized_1 = sanitize_text(raw_text_1, evidence_pack)
        assert sanitized_1 == "Results shown in [2] prove scaling."
        assert "arxiv:" not in sanitized_1
        assert "claim:" not in sanitized_1

        # 2. Mixed list of brackets merged into single [1, 2]
        raw_text_2 = "Supported by [arxiv:1905.09130v1:claim:4] and [paper_1:claim:1]."
        sanitized_2 = sanitize_text(raw_text_2, evidence_pack)
        assert sanitized_2 == "Supported by [1, 2]."
        assert "arxiv:" not in sanitized_2
        assert "claim:" not in sanitized_2

        # 3. Unknown paper removed entirely
        raw_text_3 = "Empirical study [arxiv:9999.88888:claim:9] demonstrated high accuracy."
        sanitized_3 = sanitize_text(raw_text_3, evidence_pack)
        assert sanitized_3 == "Empirical study demonstrated high accuracy."
        assert "arxiv:" not in sanitized_3
        assert "claim:" not in sanitized_3

    def test_global_no_arxiv_or_claim_in_any_slide_text(self):
        """Global assertion that no slide text field contains 'arxiv:' or 'claim:' in both LLM and fallback decks."""
        guided_input, findings, citations = sample_inputs()
        evidence_pack = build_evidence_pack(findings, citations)

        # 1. Fallback deck
        fallback_deck = build_deterministic_fallback_deck(guided_input, findings, evidence_pack, citations)
        for s in fallback_deck.slides:
            fields_to_check = [s.title, s.notes] + s.bullets + s.table_header + [cell for row in s.table_rows for cell in row]
            for text in fields_to_check:
                assert "arxiv:" not in text.lower(), f"Found 'arxiv:' in fallback slide text: {text}"
                assert ":claim:" not in text.lower(), f"Found ':claim:' in fallback slide text: {text}"
                assert "[claim" not in text.lower(), f"Found '[claim' in fallback slide text: {text}"

        # 2. LLM deck with dirty text containing raw IDs everywhere
        dirty_json = """
        {
          "slides": [
            {
              "layout": "title",
              "title": "Research on [arxiv:1905.09130v1:claim:4]",
              "bullets": ["Overview [paper_1:claim:1]"],
              "notes": "Speaker notes citing [arxiv:1905.09130v1:claim:2]"
            },
            {
              "layout": "bullets",
              "title": "Literature Findings",
              "bullets": [
                "Finding A [arxiv:1905.09130v1:claim:4]",
                "Finding B [paper_1:claim:1]"
              ],
              "claim_ids": ["claim_01", "claim_02"],
              "notes": "Notes mentioning [paper_1:claim:1]"
            }
          ]
        }
        """
        evidence_pack.paper_number_map["arxiv:1905.09130v1"] = 2
        mock_llm = FakeLLM(response_text=dirty_json)
        llm_deck = build_ppt_structured(guided_input, findings, citations, llm=mock_llm)

        for s in llm_deck.slides:
            fields_to_check = [s.title, s.notes] + s.bullets + s.table_header + [cell for row in s.table_rows for cell in row]
            for text in fields_to_check:
                assert "arxiv:" not in text.lower(), f"Found 'arxiv:' in LLM slide text: {text}"
                assert ":claim:" not in text.lower(), f"Found ':claim:' in LLM slide text: {text}"
                assert "[claim" not in text.lower(), f"Found '[claim' in LLM slide text: {text}"

    def test_ungrounded_literature_bullet_dropped(self):
        """Literature-derived bullets without any valid verified claim_id are dropped."""
        guided_input, findings, citations = sample_inputs()

        json_with_ungrounded = """
        {
          "slides": [
            {
              "layout": "title",
              "title": "Evaluation Deck",
              "bullets": ["Intro"]
            },
            {
              "layout": "bullets",
              "title": "Literature Review Themes",
              "bullets": [
                "Decoupled multi-agent systems reduce latency by 35%.",
                "Demonstrates practical effectiveness of data-driven bid-pricing in operational workflows without proof."
              ],
              "claim_ids": ["claim_01"]
            },
            {
              "layout": "bullets",
              "title": "Related Literature Inventions",
              "bullets": [
                "Completely fabricated finding with no ground in verified claims."
              ],
              "claim_ids": []
            }
          ]
        }
        """
        mock_llm = FakeLLM(response_text=json_with_ungrounded)
        structured = build_ppt_structured(guided_input, findings, citations, llm=mock_llm)

        lit_slides = [s for s in structured.slides if s.layout == "bullets" and ("Literature" in s.title or "Related" in s.title)]
        # Only the slide with grounded claim_01 survives; "Related Literature Inventions" is completely dropped
        assert len(lit_slides) == 1
        assert "Literature Review Themes" in lit_slides[0].title
        # The ungrounded bullet is dropped; grounded bullet has marker [1]
        assert len(lit_slides[0].bullets) == 1
        assert "[1]" in lit_slides[0].bullets[0]
        assert "bid-pricing" not in lit_slides[0].bullets[0]

    def test_table_has_one_row_per_paper_with_title_and_year(self):
        """The comparison table covers papers with Source as '[n] Short title (year)' and 4 columns."""
        guided_input, findings, citations = sample_inputs()
        evidence_pack = build_evidence_pack(findings, citations)

        table_slide = build_table_slide(evidence_pack, findings)
        assert table_slide.layout == "table"
        assert table_slide.table_header == ["Source", "Approach", "Key finding", "Limitation / note"]
        assert len(table_slide.table_rows) == 2

        # Check row 1
        row1 = table_slide.table_rows[0]
        assert row1[0] == "[1] Multi-Agent Scalability (2021)"
        assert row1[1] != ""
        assert row1[2] != ""

        # Check row 2
        row2 = table_slide.table_rows[1]
        assert row2[0] == "[2] Dense Retrieval at Scale (2022)"

    def test_chart_notes_match_computed_data(self):
        """Chart FigureSpec title and slide speaker notes match computed data deterministically."""
        guided_input, findings, citations = sample_inputs()
        evidence_pack = build_evidence_pack(findings, citations)

        # 1. Under 4 distinct years: Claims per source
        fig1, title1, notes1 = compute_chart_figure_and_notes(evidence_pack)
        assert fig1.data_source == "claims_per_source"
        assert fig1.title == "Verified Claims per Source"
        assert title1 == "Research Evidence Distribution"
        assert "Quantitative breakdown of 2 verified claims" in notes1
        assert "across 2 surveyed sources" in notes1

        # 2. 4 or more distinct years: Papers per year
        citations_4 = CitationResult(
            citation_style="apa",
            citations=[
                FormattedCitation(citation_id="c1", paper_id="p1", citation_style="apa", inline_marker="[1]", full_entry="Author (2019). T1."),
                FormattedCitation(citation_id="c2", paper_id="p2", citation_style="apa", inline_marker="[2]", full_entry="Author (2020). T2."),
                FormattedCitation(citation_id="c3", paper_id="p3", citation_style="apa", inline_marker="[3]", full_entry="Author (2021). T3."),
                FormattedCitation(citation_id="c4", paper_id="p4", citation_style="apa", inline_marker="[4]", full_entry="Author (2022). T4."),
            ],
        )
        findings_4 = FindingsPacket(
            topic="Trends",
            summaries=[
                PaperSummary(paper_id="p1", title="T1", year=2019, summary="S1"),
                PaperSummary(paper_id="p2", title="T2", year=2020, summary="S2"),
                PaperSummary(paper_id="p3", title="T3", year=2021, summary="S3"),
                PaperSummary(paper_id="p4", title="T4", year=2022, summary="S4"),
            ],
            claims=[
                Claim(claim_id="cl1", text="C1", source_paper_id="p1", verification_status="verified"),
                Claim(claim_id="cl2", text="C2", source_paper_id="p2", verification_status="verified"),
                Claim(claim_id="cl3", text="C3", source_paper_id="p3", verification_status="verified"),
                Claim(claim_id="cl4", text="C4", source_paper_id="p4", verification_status="verified"),
            ],
        )
        pack_4 = build_evidence_pack(findings_4, citations_4)
        fig2, title2, notes2 = compute_chart_figure_and_notes(pack_4)
        assert fig2.data_source == "papers_per_year"
        assert fig2.title == "Publications per Year"
        assert title2 == "Research Timeline & Evidence Growth"
        assert "distinct publication years (2019-2022)" in notes2

    def test_references_slide_count_and_numbering(self):
        """References slide entries formatted as '[n] First author et al. (year). Title. Venue'."""
        guided_input, findings, citations = sample_inputs()
        evidence_pack = build_evidence_pack(findings, citations)

        ref_slides = build_references_slides(evidence_pack, findings, citations)
        assert len(ref_slides) == 1
        assert ref_slides[0].layout == "bullets"
        assert ref_slides[0].title == "References"
        assert len(ref_slides[0].bullets) == 2
        assert ref_slides[0].bullets[0] == "[1] Vaswani et al. (2021). Multi-Agent Scalability. Journal of AI."
        assert ref_slides[0].bullets[1] == "[2] Smith et al. (2022). Dense Retrieval at Scale. IEEE Trans."

        # Test splitting when more than 5 references exist
        many_summaries = []
        many_citations = []
        for i in range(1, 9):
            pid = f"paper_{i}"
            many_summaries.append(
                PaperSummary(
                    paper_id=pid,
                    title=f"Paper Title {i}",
                    authors=[f"Author_{i}"],
                    year=2020 + i,
                    venue=f"Venue_{i}",
                    summary=f"Summary {i}",
                )
            )
            many_citations.append(
                FormattedCitation(
                    citation_id=f"cit_{i}",
                    paper_id=pid,
                    citation_style="apa",
                    inline_marker=f"[{i}]",
                    full_entry=f"Author_{i} ({2020 + i}). Paper Title {i}. Venue_{i}.",
                )
            )
        many_findings = FindingsPacket(topic="Large Corpus", summaries=many_summaries, claims=[])
        many_cit_result = CitationResult(citation_style="apa", citations=many_citations)
        many_pack = build_evidence_pack(many_findings, many_cit_result)

        split_ref_slides = build_references_slides(many_pack, many_findings, many_cit_result)
        # 8 references split into chunks of max 5: 5 in slide 1, 3 in slide 2
        assert len(split_ref_slides) == 2
        assert len(split_ref_slides[0].bullets) == 5
        assert len(split_ref_slides[1].bullets) == 3
        assert split_ref_slides[0].title == "References (1/2)"
        assert split_ref_slides[1].title == "References (2/2)"
        assert split_ref_slides[0].bullets[0].startswith("[1]")
        assert split_ref_slides[1].bullets[2].startswith("[8]")

    def test_contradictions_slide_present_only_when_details_exist(self):
        """Contradictions slide added only when findings.contradiction_details is non-empty."""
        guided_input, findings, citations = sample_inputs()
        evidence_pack = build_evidence_pack(findings, citations)

        # 1. When empty: no slide generated
        assert len(findings.contradiction_details) == 0
        contra_slide_empty = build_contradictions_slide(findings, evidence_pack)
        assert contra_slide_empty is None

        # 2. When details exist: generates 'Conflicting or Open Findings' slide
        findings.contradiction_details = [
            ContradictionDetail(
                claim_a_id="claim_01",
                claim_b_id="claim_02",
                paper_a_id="paper_1",
                paper_b_id="paper_2",
                explanation="Paper 1 demonstrates latency reduction whereas Paper 2 identifies retrieval bottlenecks under scale.",
                shared_subject="Multi-agent retrieval efficiency",
            )
        ]
        contra_slide_active = build_contradictions_slide(findings, evidence_pack)
        assert contra_slide_active is not None
        assert contra_slide_active.title == "Conflicting or Open Findings"
        assert len(contra_slide_active.bullets) == 1
        assert "[1]" in contra_slide_active.bullets[0]
        assert "[2]" in contra_slide_active.bullets[0]
        assert "Paper 1 demonstrates latency reduction" in contra_slide_active.bullets[0]

    def test_tech_stack_appears_only_once(self):
        """Tech stack appears on its dedicated slide and is not duplicated in Own Results."""
        guided_input, findings, citations = sample_inputs()

        # LLM tries to duplicate tech stack in Own Results
        duplicate_json = """
        {
          "slides": [
            {
              "layout": "title",
              "title": "Title",
              "bullets": ["Sub"]
            },
            {
              "layout": "bullets",
              "title": "Own Results",
              "bullets": [
                "Achieved 35 percent speedup.",
                "Built using Python, LangGraph, and ChromaDB.",
                "Zero hallucination citations."
              ]
            },
            {
              "layout": "bullets",
              "title": "Tech Stack & Implementation",
              "bullets": ["Python", "LangGraph", "ChromaDB"]
            }
          ]
        }
        """
        mock_llm = FakeLLM(response_text=duplicate_json)
        structured = build_ppt_structured(guided_input, findings, citations, llm=mock_llm)

        tech_stack_slides = [s for s in structured.slides if "tech stack" in s.title.lower()]
        results_slides = [s for s in structured.slides if "result" in s.title.lower()]

        # Tech stack slide exists
        assert len(tech_stack_slides) == 1
        assert "Python" in tech_stack_slides[0].bullets

        # Own results does not repeat the tech stack items
        assert len(results_slides) >= 1
        for res_slide in results_slides:
            for b in res_slide.bullets:
                assert "Built using Python" not in b
                assert "ChromaDB" not in b
