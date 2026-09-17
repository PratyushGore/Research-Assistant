from enum import Enum
from typing import Optional
from pydantic import BaseModel, Field


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


class FindingsPacket(BaseModel):
    topic: str
    summaries: list[PaperSummary] = Field(default_factory=list)
    claims: list[Claim] = Field(default_factory=list)


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


class ComposerResult(BaseModel):
    output_type: OutputType
    title: str
    content: str
    sections: dict[str, str] = Field(default_factory=dict)
    citations_used: list[str] = Field(default_factory=list)


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
    request_id: str
    status: str = "pending"
    current_agent: Optional[str] = None
    completed_deliverables: list[ComposerResult] = Field(default_factory=list)
    error_message: Optional[str] = None
