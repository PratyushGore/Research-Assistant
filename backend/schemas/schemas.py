from enum import Enum
from typing import Literal, Optional
from pydantic import BaseModel, Field, field_validator


class OutputType(str, Enum):
    LITERATURE_SURVEY = "literature_survey"
    EXECUTIVE_SUMMARY = "executive_summary"
    PPT = "ppt"
    RESEARCH_PAPER = "research_paper"


class CoverInfo(BaseModel):
    title: str
    subtitle: Optional[str] = None
    authors: list[str] = Field(default_factory=list)
    institution: Optional[str] = None
    date: Optional[str] = None


class ProjectPresentationInfo(BaseModel):
    problem_statement: str
    tech_stack: list[str]
    own_architecture_summary: str
    own_results_summary: str
    project_timeline: Optional[str] = None


class AcademicContentInfo(BaseModel):
    methodology: str
    dataset_or_sample: str
    tools_used: list[str]
    what_was_measured: str
    key_results: str
    limitations: Optional[str] = None


class OutputTemplate(BaseModel):
    template_id: str
    output_type: OutputType
    sections: list[str] = Field(default_factory=list)
    guidelines: Optional[str] = None


class GuidedInputBundle(BaseModel):
    cover_info: CoverInfo
    project_presentation_info: Optional[ProjectPresentationInfo] = None
    academic_content_info: Optional[AcademicContentInfo] = None


class PaperMetadata(BaseModel):
    paper_id: str
    title: str
    authors: list[str] = Field(default_factory=list)
    abstract: Optional[str] = None
    year: Optional[int] = None
    url: Optional[str] = None
    venue: Optional[str] = None
    doi: Optional[str] = None


class SearchResult(BaseModel):
    query: str
    papers: list[PaperMetadata] = Field(default_factory=list)
    total_results: int = 0


class Chunk(BaseModel):
    chunk_id: str
    paper_id: str
    text: str
    section_heading: Optional[str] = None
    page_number: Optional[int] = None


class IngestionResult(BaseModel):
    paper_id: str
    metadata: PaperMetadata
    chunks: list[Chunk] = Field(default_factory=list)
    raw_text: Optional[str] = None


class Claim(BaseModel):
    claim_id: str
    text: str
    source_paper_id: str
    source_chunk_ids: list[str] = Field(default_factory=list)
    verification_status: str = "pending"
    revision_attempts: int = 0


class PaperSummary(BaseModel):
    paper_id: str
    summary: str
    key_findings: list[str] = Field(default_factory=list)
    extracted_claims: list[Claim] = Field(default_factory=list)
    title: Optional[str] = None
    authors: list[str] = Field(default_factory=list)
    year: Optional[int] = None
    venue: Optional[str] = None
    url: Optional[str] = None


class ContradictionDetail(BaseModel):
    claim_a_id: str
    claim_b_id: str
    paper_a_id: str
    paper_b_id: str
    explanation: str
    shared_subject: str
    extra_claim_ids: list[str] = Field(default_factory=list)


class FindingsPacket(BaseModel):
    topic: str
    summaries: list[PaperSummary] = Field(default_factory=list)
    claims: list[Claim] = Field(default_factory=list)
    contradictions: list[str] = Field(default_factory=list)
    contradiction_details: list[ContradictionDetail] = Field(default_factory=list)
    cross_paper_synthesis: Optional[str] = None
    requested_papers: Optional[int] = None
    available_papers: Optional[int] = None
    paper_notice: Optional[str] = None


class VerificationResult(BaseModel):
    claim_id: str
    verification_status: str
    confidence_score: float = 0.0
    explanation: str = ""
    supporting_chunk_ids: list[str] = Field(default_factory=list)


class FormattedCitation(BaseModel):
    citation_id: str
    paper_id: str
    citation_style: str
    inline_marker: str
    full_entry: str


class CitationResult(BaseModel):
    citation_style: str
    citations: list[FormattedCitation] = Field(default_factory=list)
    bibliography: list[str] = Field(default_factory=list)


class ComposerRequest(BaseModel):
    output_type: OutputType
    guided_input: GuidedInputBundle
    findings: FindingsPacket
    verification_results: list[VerificationResult] = Field(default_factory=list)
    citation_result: CitationResult
    template: Optional[OutputTemplate] = None


class FigureSpec(BaseModel):
    figure_id: str
    kind: Literal["bar_chart", "diagram"]
    title: str
    labels: list[str] = Field(default_factory=list)
    values: list[float] = Field(default_factory=list)
    data_source: Optional[str] = None
    nodes: list[str] = Field(default_factory=list)
    edges: list[tuple[str, str]] = Field(default_factory=list)


class ContentBlock(BaseModel):
    kind: Literal["paragraph", "bullets", "table", "callout", "key_numbers", "figure"]
    text: Optional[str] = None
    items: list[str] = Field(default_factory=list)
    table_header: list[str] = Field(default_factory=list)
    table_rows: list[list[str]] = Field(default_factory=list)
    caption: Optional[str] = None
    figure_id: Optional[str] = None
    claim_ids: list[str] = Field(default_factory=list)


class DocSection(BaseModel):
    heading: str
    blocks: list[ContentBlock] = Field(default_factory=list)


class SlideSpec(BaseModel):
    layout: Literal[
        "title",
        "agenda",
        "section_divider",
        "bullets",
        "table",
        "chart",
        "diagram",
        "closing",
    ]
    title: str
    bullets: list[str] = Field(default_factory=list)
    table_header: list[str] = Field(default_factory=list)
    table_rows: list[list[str]] = Field(default_factory=list)
    figure_id: Optional[str] = None
    notes: Optional[str] = None
    claim_ids: list[str] = Field(default_factory=list)

    @field_validator("bullets")
    @classmethod
    def validate_bullets_max_five(cls, v: list[str]) -> list[str]:
        if len(v) > 5:
            raise ValueError("Slide bullets list cannot exceed 5 items.")
        return v


class StructuredContent(BaseModel):
    sections: list[DocSection] = Field(default_factory=list)
    slides: list[SlideSpec] = Field(default_factory=list)
    figures: list[FigureSpec] = Field(default_factory=list)


class ComposerResult(BaseModel):
    output_type: OutputType
    title: str
    content: str
    sections: dict[str, str] = Field(default_factory=dict)
    citations_used: list[str] = Field(default_factory=list)
    file_path: Optional[str] = None
    structured: Optional[StructuredContent] = None


class DocumentReviewRequest(BaseModel):
    composer_result: ComposerResult
    findings: FindingsPacket
    verification_results: list[VerificationResult] = Field(default_factory=list)
    citation_result: CitationResult


class DocumentReviewResult(BaseModel):
    passed: bool
    score: float = 0.0
    feedback: str = ""
    issues: list[str] = Field(default_factory=list)
    suggested_revisions: Optional[str] = None


class UserQARequest(BaseModel):
    question: str
    topic: str


class UserQAResponse(BaseModel):
    answer: str
    source_paper_ids: list[str] = Field(default_factory=list)


class PipelineRequest(BaseModel):
    request_id: str
    topic: str
    selected_outputs: list[OutputType]


class PipelineStatus(BaseModel):
    request_id: Optional[str] = None
    stage: str = "pending"
    detail: Optional[str] = None
    progress_pct: Optional[int] = None
    status: str = "pending"
    current_agent: Optional[str] = None
    completed_deliverables: list[ComposerResult] = Field(default_factory=list)
    error_message: Optional[str] = None
