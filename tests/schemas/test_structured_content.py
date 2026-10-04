import pytest
from pydantic import ValidationError

from backend.schemas.schemas import (
    ComposerResult,
    ContentBlock,
    DocSection,
    FigureSpec,
    OutputType,
    SlideSpec,
    StructuredContent,
)


class TestFigureSpec:
    def test_valid_bar_chart(self):
        fig = FigureSpec(
            figure_id="fig_1",
            kind="bar_chart",
            title="Papers Published per Year",
            labels=["2021", "2022", "2023"],
            values=[5.0, 12.0, 18.0],
            data_source="papers_per_year",
        )
        assert fig.figure_id == "fig_1"
        assert fig.kind == "bar_chart"
        assert fig.title == "Papers Published per Year"
        assert fig.labels == ["2021", "2022", "2023"]
        assert fig.values == [5.0, 12.0, 18.0]
        assert fig.data_source == "papers_per_year"
        assert fig.nodes == []
        assert fig.edges == []

    def test_valid_diagram(self):
        fig = FigureSpec(
            figure_id="diag_1",
            kind="diagram",
            title="System Architecture",
            nodes=["Search", "Ingestion", "Composer"],
            edges=[("Search", "Ingestion"), ("Ingestion", "Composer")],
        )
        assert fig.figure_id == "diag_1"
        assert fig.kind == "diagram"
        assert fig.nodes == ["Search", "Ingestion", "Composer"]
        assert fig.edges == [("Search", "Ingestion"), ("Ingestion", "Composer")]
        assert fig.labels == []
        assert fig.values == []
        assert fig.data_source is None

    def test_invalid_kind(self):
        with pytest.raises(ValidationError):
            FigureSpec(
                figure_id="fig_bad",
                kind="pie_chart",  # type: ignore
                title="Invalid Kind",
            )


class TestContentBlock:
    @pytest.mark.parametrize(
        "kind",
        ["paragraph", "bullets", "table", "callout", "key_numbers", "figure"],
    )
    def test_valid_kinds(self, kind):
        block = ContentBlock(kind=kind, text="Sample text")
        assert block.kind == kind
        assert block.text == "Sample text"
        assert block.items == []
        assert block.table_header == []
        assert block.table_rows == []
        assert block.caption is None
        assert block.figure_id is None
        assert block.claim_ids == []

    def test_invalid_kind(self):
        with pytest.raises(ValidationError):
            ContentBlock(kind="unknown_kind")  # type: ignore

    def test_table_block(self):
        block = ContentBlock(
            kind="table",
            table_header=["Metric", "Value"],
            table_rows=[["Accuracy", "95%"], ["Latency", "12ms"]],
            caption="Performance Overview",
            claim_ids=["claim_1"],
        )
        assert block.table_header == ["Metric", "Value"]
        assert len(block.table_rows) == 2
        assert block.caption == "Performance Overview"
        assert block.claim_ids == ["claim_1"]


class TestDocSection:
    def test_valid_doc_section_default(self):
        sec = DocSection(heading="Introduction")
        assert sec.heading == "Introduction"
        assert sec.blocks == []

    def test_doc_section_with_blocks(self):
        sec = DocSection(
            heading="Methodology",
            blocks=[
                ContentBlock(kind="paragraph", text="We conducted a systematic review."),
                ContentBlock(kind="bullets", items=["Step 1", "Step 2"]),
            ],
        )
        assert sec.heading == "Methodology"
        assert len(sec.blocks) == 2
        assert sec.blocks[0].kind == "paragraph"
        assert sec.blocks[1].items == ["Step 1", "Step 2"]


class TestSlideSpec:
    @pytest.mark.parametrize(
        "layout",
        [
            "title",
            "agenda",
            "section_divider",
            "bullets",
            "table",
            "chart",
            "diagram",
            "closing",
        ],
    )
    def test_valid_layouts(self, layout):
        slide = SlideSpec(layout=layout, title=f"Slide for {layout}")
        assert slide.layout == layout
        assert slide.bullets == []

    def test_bullets_up_to_five_allowed(self):
        # 0 bullets
        s0 = SlideSpec(layout="bullets", title="Zero", bullets=[])
        assert len(s0.bullets) == 0

        # 3 bullets
        s3 = SlideSpec(layout="bullets", title="Three", bullets=["a", "b", "c"])
        assert len(s3.bullets) == 3

        # 5 bullets
        s5 = SlideSpec(layout="bullets", title="Five", bullets=["1", "2", "3", "4", "5"])
        assert len(s5.bullets) == 5

    def test_bullets_exceeding_five_rejected(self):
        with pytest.raises(ValidationError) as exc_info:
            SlideSpec(
                layout="bullets",
                title="Too Many Bullets",
                bullets=["1", "2", "3", "4", "5", "6"],
            )
        assert "5" in str(exc_info.value)

    def test_invalid_layout(self):
        with pytest.raises(ValidationError):
            SlideSpec(layout="invalid_layout", title="Invalid")  # type: ignore


class TestStructuredContent:
    def test_defaults(self):
        sc = StructuredContent()
        assert sc.sections == []
        assert sc.slides == []
        assert sc.figures == []

    def test_populated(self):
        sc = StructuredContent(
            sections=[DocSection(heading="Sec 1")],
            slides=[SlideSpec(layout="title", title="Intro")],
            figures=[FigureSpec(figure_id="f1", kind="bar_chart", title="Chart")],
        )
        assert len(sc.sections) == 1
        assert len(sc.slides) == 1
        assert len(sc.figures) == 1


class TestComposerResultCompatibility:
    def test_composer_result_validates_without_structured(self):
        cr = ComposerResult(
            output_type=OutputType.LITERATURE_SURVEY,
            title="Survey Title",
            content="Full document text",
            sections={"Intro": "Intro content", "Methods": "Methods content"},
            citations_used=["cit_1"],
            file_path="/path/to/file.docx",
        )
        assert cr.title == "Survey Title"
        assert cr.content == "Full document text"
        assert cr.sections == {"Intro": "Intro content", "Methods": "Methods content"}
        assert cr.citations_used == ["cit_1"]
        assert cr.file_path == "/path/to/file.docx"
        assert cr.structured is None

    def test_composer_result_roundtrip_with_structured(self):
        fig = FigureSpec(
            figure_id="fig_1",
            kind="bar_chart",
            title="Publication Trends",
            labels=["2020", "2021"],
            values=[10.0, 25.0],
            data_source="trends",
        )
        section = DocSection(
            heading="Findings",
            blocks=[
                ContentBlock(
                    kind="paragraph",
                    text="Paragraph text with grounded claim.",
                    claim_ids=["claim_1"],
                ),
                ContentBlock(
                    kind="figure",
                    figure_id="fig_1",
                    caption="Figure 1: Trends",
                ),
            ],
        )
        slide = SlideSpec(
            layout="bullets",
            title="Key Takeaways",
            bullets=["Point 1", "Point 2", "Point 3"],
            claim_ids=["claim_1"],
        )
        structured = StructuredContent(
            sections=[section],
            slides=[slide],
            figures=[fig],
        )

        cr = ComposerResult(
            output_type=OutputType.PPT,
            title="Presentation Title",
            content="Summary content",
            sections={"Key Takeaways": "Point 1\nPoint 2\nPoint 3"},
            citations_used=["cit_1"],
            file_path="/path/to/pres.pptx",
            structured=structured,
        )

        # model_dump and model_validate roundtrip
        dumped = cr.model_dump()
        assert dumped["structured"] is not None
        assert dumped["structured"]["sections"][0]["heading"] == "Findings"
        assert dumped["structured"]["slides"][0]["bullets"] == ["Point 1", "Point 2", "Point 3"]
        assert dumped["structured"]["figures"][0]["title"] == "Publication Trends"

        validated = ComposerResult.model_validate(dumped)
        assert validated.structured is not None
        assert len(validated.structured.sections) == 1
        assert validated.structured.sections[0].heading == "Findings"
        assert validated.structured.slides[0].bullets == ["Point 1", "Point 2", "Point 3"]
        assert validated.structured.figures[0].values == [10.0, 25.0]

        # JSON roundtrip
        json_str = cr.model_dump_json()
        validated_json = ComposerResult.model_validate_json(json_str)
        assert validated_json.structured is not None
        assert validated_json.structured.figures[0].figure_id == "fig_1"
