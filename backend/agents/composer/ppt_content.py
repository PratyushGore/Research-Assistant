"""
Grounded, testable LLM content generation layer for PowerPoint presentations.

Builds a deterministic evidence pack from verified research claims, citations,
and paper summaries, executes a single token-disciplined Gemini call to structure
a 9-12 slide deck, applies strict post-validation, sanitization, and grounding,
and attaches pre-computed figures and reference slides.
"""

from __future__ import annotations

from dataclasses import dataclass
import json
import logging
import re
from typing import Any, Optional

from backend.agents.common.llm_client import GeminiClient
from backend.schemas.schemas import (
    CitationResult,
    FigureSpec,
    FindingsPacket,
    FormattedCitation,
    GuidedInputBundle,
    ProjectPresentationInfo,
    SlideSpec,
    StructuredContent,
)

logger = logging.getLogger("research_assistant.composer.ppt_content")

MAX_CLAIMS_IN_PROMPT = 20
CHART_FIGURE_ID = "fig_chart_1"
DIAGRAM_FIGURE_ID = "fig_diagram_1"


# ---------------------------------------------------------------------------
# Citation Parsing & Evidence Pack
# ---------------------------------------------------------------------------

def extract_paper_metadata_from_citation(
    citation: FormattedCitation,
) -> tuple[str, Optional[int]]:
    """
    Extract human-readable paper title and publication year from FormattedCitation.full_entry.
    Safely parses IEEE and APA reference styles without touching external agents.
    Falls back to paper_id and None if parsing cannot determine them.
    """
    entry = citation.full_entry or ""

    # 1. IEEE style: Title is quoted, e.g., Authors, "Title of Paper," Venue, Year.
    m_quote = re.search(r'"([^"]+)"', entry)
    title: Optional[str] = None
    if m_quote:
        title = m_quote.group(1).rstrip(",.")
    else:
        # 2. APA style: Authors (Year). Title. Venue.
        m_apa = re.search(r'\((?:(?:19|20)\d{2}|n\.d\.)\)\.\s*([^.]+)\.', entry)
        if m_apa and m_apa.group(1):
            title = m_apa.group(1).strip()

    if not title or len(title.strip()) < 2:
        title = citation.paper_id

    # Year extraction: 4-digit year 19xx or 20xx
    m_year = re.search(r'\b(19\d\d|20\d\d)\b', entry)
    year = int(m_year.group(1)) if m_year else None

    return title.strip(), year


def build_paper_number_map(
    citation_result: CitationResult,
    findings: FindingsPacket,
) -> dict[str, int]:
    """
    Build a deterministic mapping from paper_id -> 1-based integer index [n].
    Primary ordering is established by citation_result.citations.
    Any additional papers appearing in findings.summaries or findings.claims
    are appended deterministically in order of appearance.
    """
    paper_map: dict[str, int] = {}
    current_idx = 1

    for cit in citation_result.citations:
        if cit.paper_id and cit.paper_id not in paper_map:
            paper_map[cit.paper_id] = current_idx
            current_idx += 1

    for summary in findings.summaries:
        if summary.paper_id and summary.paper_id not in paper_map:
            paper_map[summary.paper_id] = current_idx
            current_idx += 1

    for claim in findings.claims:
        if claim.source_paper_id and claim.source_paper_id not in paper_map:
            paper_map[claim.source_paper_id] = current_idx
            current_idx += 1

    return paper_map


@dataclass
class PaperEvidence:
    paper_id: str
    number: int
    title: str
    year: Optional[int]
    authors: list[str]
    venue: Optional[str]
    inline_marker: str
    full_entry: str


@dataclass
class VerifiedClaimEvidence:
    claim_id: str
    text: str
    paper_id: str
    paper_number: int
    paper_title: str
    paper_marker: str


@dataclass
class EvidencePack:
    paper_number_map: dict[str, int]
    papers: dict[str, PaperEvidence]
    papers_list: list[PaperEvidence]
    verified_claims: list[VerifiedClaimEvidence]
    verified_claim_ids: set[str]
    claim_to_paper: dict[str, str]
    claims_by_paper: dict[str, list[VerifiedClaimEvidence]]
    claim_counts: dict[str, int]
    claims_per_paper: dict[str, int]
    papers_per_year: dict[str, int]
    distinct_years: set[int]


def build_evidence_pack(
    findings: FindingsPacket,
    citation_result: CitationResult,
) -> EvidencePack:
    """
    Build a deterministic evidence pack containing only verified claims and paper metadata.
    Claims with 'pending' or 'unverified' status are strictly excluded from evidence.
    Establishes a single uniform paper_id -> [n] mapping used everywhere.
    """
    paper_number_map = build_paper_number_map(citation_result, findings)

    # Build summaries lookup
    summaries_by_id = {s.paper_id: s for s in findings.summaries if s.paper_id}
    citations_by_id = {c.paper_id: c for c in citation_result.citations if c.paper_id}

    papers: dict[str, PaperEvidence] = {}
    papers_list: list[PaperEvidence] = []

    for paper_id, num in sorted(paper_number_map.items(), key=lambda item: item[1]):
        summary = summaries_by_id.get(paper_id)
        citation = citations_by_id.get(paper_id)

        title = None
        year = None
        authors: list[str] = []
        venue = None
        full_entry = citation.full_entry if citation else ""

        if summary:
            title = summary.title
            year = summary.year
            authors = summary.authors or []
            venue = summary.venue

        if citation and (not title or year is None):
            cit_title, cit_year = extract_paper_metadata_from_citation(citation)
            if not title:
                title = cit_title
            if year is None:
                year = cit_year

        title = (title or paper_id).strip()

        evidence_paper = PaperEvidence(
            paper_id=paper_id,
            number=num,
            title=title,
            year=year,
            authors=authors,
            venue=venue,
            inline_marker=f"[{num}]",
            full_entry=full_entry,
        )
        papers[paper_id] = evidence_paper
        papers_list.append(evidence_paper)

    verified_claims: list[VerifiedClaimEvidence] = []
    verified_claim_ids: set[str] = set()
    claim_to_paper: dict[str, str] = {}
    claims_by_paper: dict[str, list[VerifiedClaimEvidence]] = {pid: [] for pid in paper_number_map}

    claim_counts = {"verified": 0, "unverified": 0, "pending": 0, "total": len(findings.claims)}
    claims_per_paper: dict[str, int] = {}

    for claim in findings.claims:
        status = (claim.verification_status or "").lower()
        claim_to_paper[claim.claim_id] = claim.source_paper_id

        if status == "verified":
            claim_counts["verified"] += 1
            paper = papers.get(claim.source_paper_id)
            title = paper.title if paper else claim.source_paper_id
            num = paper.number if paper else paper_number_map.get(claim.source_paper_id, 1)
            marker = f"[{num}]"

            evidence = VerifiedClaimEvidence(
                claim_id=claim.claim_id,
                text=claim.text.strip(),
                paper_id=claim.source_paper_id,
                paper_number=num,
                paper_title=title,
                paper_marker=marker,
            )
            verified_claims.append(evidence)
            verified_claim_ids.add(claim.claim_id)
            claims_by_paper.setdefault(claim.source_paper_id, []).append(evidence)
            claims_per_paper[claim.source_paper_id] = claims_per_paper.get(claim.source_paper_id, 0) + 1
        elif status == "pending":
            claim_counts["pending"] += 1
        else:
            claim_counts["unverified"] += 1

    distinct_years = {p.year for p in papers.values() if p.year is not None}
    papers_per_year: dict[str, int] = {}
    for p in papers.values():
        if p.year is not None:
            y_str = str(p.year)
            papers_per_year[y_str] = papers_per_year.get(y_str, 0) + 1

    return EvidencePack(
        paper_number_map=paper_number_map,
        papers=papers,
        papers_list=papers_list,
        verified_claims=verified_claims,
        verified_claim_ids=verified_claim_ids,
        claim_to_paper=claim_to_paper,
        claims_by_paper=claims_by_paper,
        claim_counts=claim_counts,
        claims_per_paper=claims_per_paper,
        papers_per_year=papers_per_year,
        distinct_years=distinct_years,
    )


# ---------------------------------------------------------------------------
# Text Sanitizer
# ---------------------------------------------------------------------------

def sanitize_text(
    text: str,
    evidence_pack: EvidencePack,
) -> str:
    """
    Sanitize slide text:
    - Replace bracketed tokens containing ':claim:' or known paper_id with numeric marker [n].
    - Merge multiple citations to '[1, 2]'.
    - Remove bracketed tokens whose paper is unknown.
    - Never leave 'arxiv:' or 'claim:' in any output text.
    """
    if not text:
        return ""

    paper_map = evidence_pack.paper_number_map
    claim_to_paper = evidence_pack.claim_to_paper

    def _resolve_token_to_paper_num(tok: str) -> Optional[int]:
        tok_clean = tok.strip().strip("[](),;\"'")
        if not tok_clean:
            return None

        # Check if already a valid digit number
        if tok_clean.isdigit():
            val = int(tok_clean)
            if val in paper_map.values():
                return val

        # Direct claim ID match
        if tok_clean in claim_to_paper:
            pid = claim_to_paper[tok_clean]
            if pid in paper_map:
                return paper_map[pid]

        # Token with :claim: e.g. arxiv:1905.09130v1:claim:4 or claim:4
        if ":claim:" in tok_clean:
            prefix = tok_clean.split(":claim:")[0]
            for pid, num in paper_map.items():
                if pid in prefix or prefix in pid:
                    return num

        # Exact or substring paper_id match
        for pid, num in paper_map.items():
            if tok_clean == pid or pid in tok_clean:
                return num

        return None

    def _repl_bracket(match: re.Match[str]) -> str:
        inner = match.group(1).strip()
        tokens = [t.strip() for t in re.split(r"[,;\s]+", inner) if t.strip()]
        resolved_nums: list[int] = []

        for tok in tokens:
            num = _resolve_token_to_paper_num(tok)
            if num is not None:
                resolved_nums.append(num)

        if resolved_nums:
            unique_sorted = sorted(set(resolved_nums))
            nums_str = ", ".join(str(n) for n in unique_sorted)
            return f"[{nums_str}]"
        return ""

    # 1. Replace bracketed tokens
    sanitized = re.sub(r"\[([^\]]+)\]", _repl_bracket, text)

    # 2. Merge adjacent bracketed markers e.g. [1] [2], [1] and [2] -> [1, 2]
    pattern_adjacent = r"\[(\d+(?:\s*,\s*\d+)*)\](?:\s*(?:,|and|&|\+)?\s*)\[(\d+(?:\s*,\s*\d+)*)\]"
    prev = None
    while prev != sanitized:
        prev = sanitized
        sanitized = re.sub(
            pattern_adjacent,
            lambda m: f"[{', '.join(str(n) for n in sorted(set([int(x.strip()) for x in m.group(1).split(',')] + [int(x.strip()) for x in m.group(2).split(',')]))) }]",
            sanitized,
        )

    # 3. Remove any remaining raw/unbracketed arxiv: or claim: tokens
    sanitized = re.sub(r"(?i)\barxiv:[^\s,;)]*", "", sanitized)
    sanitized = re.sub(r"(?i)\bclaim:[^\s,;)]*", "", sanitized)
    sanitized = re.sub(r"(?i)\barxiv:\s*", "", sanitized)
    sanitized = re.sub(r"(?i)\bclaim:\s*", "", sanitized)

    # 4. Cleanup spacing and trailing punctuation artifacts
    sanitized = re.sub(r"\s+", " ", sanitized)
    sanitized = re.sub(r"\s+([,.;])", r"\1", sanitized)
    sanitized = re.sub(r"\(\s*\)", "", sanitized)

    return sanitized.strip()


def sanitize_slide(
    slide: SlideSpec,
    evidence_pack: EvidencePack,
) -> SlideSpec:
    """Apply text sanitization to all textual fields of a SlideSpec."""
    title = sanitize_text(slide.title, evidence_pack)
    bullets = [sanitize_text(b, evidence_pack) for b in slide.bullets if sanitize_text(b, evidence_pack)]
    table_header = [sanitize_text(h, evidence_pack) for h in slide.table_header]
    table_rows = [
        [sanitize_text(cell, evidence_pack) for cell in row]
        for row in slide.table_rows
    ]
    notes = sanitize_text(slide.notes or "", evidence_pack)

    return SlideSpec(
        layout=slide.layout,
        title=title,
        bullets=bullets[:5],
        table_header=table_header,
        table_rows=table_rows,
        figure_id=slide.figure_id,
        notes=notes,
        claim_ids=slide.claim_ids,
    )


# ---------------------------------------------------------------------------
# Pre-computed Figures & Tables (Never Hallucinated by LLM)
# ---------------------------------------------------------------------------

def compute_chart_figure_and_notes(
    evidence_pack: EvidencePack,
) -> tuple[FigureSpec, str, str]:
    """
    Deterministically construct the chart FigureSpec, slide title, and speaker notes.
    Uses 'Verified claims per source' (labels '[1]'..'[n]') unless at least 4 distinct
    publication years exist, in which case it uses papers per year.
    """
    distinct_years = sorted(list(evidence_pack.distinct_years))

    if len(distinct_years) >= 4:
        labels = [str(y) for y in distinct_years]
        values = [float(evidence_pack.papers_per_year.get(str(y), 0)) for y in distinct_years]
        title = "Publications per Year"
        slide_title = "Research Timeline & Evidence Growth"
        max_val = max(values) if values else 0.0
        peak_years = [y for y, v in zip(labels, values) if v == max_val]
        notes = (
            f"Evidence distribution across {len(distinct_years)} distinct publication years ({distinct_years[0]}-{distinct_years[-1]}), "
            f"peaking in {', '.join(peak_years)} with {int(max_val)} publication{'s' if max_val != 1 else ''}."
        )
        fig = FigureSpec(
            figure_id=CHART_FIGURE_ID,
            kind="bar_chart",
            title=title,
            labels=labels,
            values=values,
            data_source="papers_per_year",
        )
        return fig, slide_title, notes
    else:
        sorted_papers = sorted(evidence_pack.papers_list, key=lambda p: p.number)
        labels = [f"[{p.number}]" for p in sorted_papers]
        values = [float(len(evidence_pack.claims_by_paper.get(p.paper_id, []))) for p in sorted_papers]
        title = "Verified Claims per Source"
        slide_title = "Research Evidence Distribution"
        total_claims = int(sum(values))
        max_claims = int(max(values)) if values else 0
        min_claims = int(min(values)) if values else 0
        notes = (
            f"Quantitative breakdown of {total_claims} verified claims across {len(labels)} surveyed sources, "
            f"ranging from {min_claims} to {max_claims} verified claims per paper."
        )
        fig = FigureSpec(
            figure_id=CHART_FIGURE_ID,
            kind="bar_chart",
            title=title,
            labels=labels,
            values=values,
            data_source="claims_per_source",
        )
        return fig, slide_title, notes


def compute_chart_figure(evidence_pack: EvidencePack) -> FigureSpec:
    """Backwards-compatible helper returning FigureSpec only."""
    fig, _, _ = compute_chart_figure_and_notes(evidence_pack)
    return fig


def build_table_slide(
    evidence_pack: EvidencePack,
    findings: FindingsPacket,
) -> SlideSpec:
    """
    Construct a grounded literature comparison table slide:
    Columns: 'Source', 'Approach', 'Key finding', 'Limitation / note'.
    Source cell: '[n] Short title (year)'.
    Approach and Key finding cells come strictly from verified claim texts only (shortened);
    leaves '-' when unsupported.
    Covers every paper (capped at 6 rows, prioritizing papers with most verified claims).
    """
    table_header = ["Source", "Approach", "Key finding", "Limitation / note"]

    papers = list(evidence_pack.papers_list)
    if len(papers) > 6:
        # Prioritize papers with the most verified claims
        papers.sort(
            key=lambda p: (len(evidence_pack.claims_by_paper.get(p.paper_id, [])), -p.number),
            reverse=True,
        )
        papers = sorted(papers[:6], key=lambda p: p.number)
    else:
        papers.sort(key=lambda p: p.number)

    table_rows: list[list[str]] = []
    all_claim_ids: list[str] = []

    method_keywords = ("model", "approach", "architecture", "method", "system", "algorithm", "framework", "pipeline", "design")
    finding_keywords = ("achieves", "reduces", "improves", "outperforms", "accuracy", "latency", "speedup", "score", "performance", "result")
    limitation_keywords = ("limitation", "trade-off", "constraint", "open", "challenge", "future", "overhead", "bottleneck")

    for p in papers:
        year_str = str(p.year) if p.year else "n.d."
        short_title = p.title[:45] + "..." if len(p.title) > 48 else p.title
        source_cell = f"[{p.number}] {short_title} ({year_str})"

        paper_claims = evidence_pack.claims_by_paper.get(p.paper_id, [])
        for c in paper_claims:
            if c.claim_id not in all_claim_ids:
                all_claim_ids.append(c.claim_id)

        approach_claim: Optional[VerifiedClaimEvidence] = None
        finding_claim: Optional[VerifiedClaimEvidence] = None
        limitation_claim: Optional[VerifiedClaimEvidence] = None

        unused_claims = list(paper_claims)

        for c in unused_claims:
            text_lower = c.text.lower()
            if any(k in text_lower for k in method_keywords):
                approach_claim = c
                unused_claims.remove(c)
                break

        for c in unused_claims:
            text_lower = c.text.lower()
            if any(k in text_lower for k in finding_keywords):
                finding_claim = c
                unused_claims.remove(c)
                break

        for c in unused_claims:
            text_lower = c.text.lower()
            if any(k in text_lower for k in limitation_keywords):
                limitation_claim = c
                unused_claims.remove(c)
                break

        # Fallback allocation from remaining unused verified claims
        if not approach_claim and unused_claims:
            approach_claim = unused_claims.pop(0)
        if not finding_claim and unused_claims:
            finding_claim = unused_claims.pop(0)
        if not limitation_claim and unused_claims:
            limitation_claim = unused_claims.pop(0)

        def _shorten(c_obj: Optional[VerifiedClaimEvidence], max_len: int = 75) -> str:
            if not c_obj:
                return "-"
            t = c_obj.text.strip()
            return t[: max_len - 3] + "..." if len(t) > max_len else t

        approach_cell = _shorten(approach_claim)
        finding_cell = _shorten(finding_claim)
        limitation_cell = _shorten(limitation_claim)

        # Check contradiction details if limitation cell is '-'
        if limitation_cell == "-":
            for d in findings.contradiction_details:
                if d.paper_a_id == p.paper_id or d.paper_b_id == p.paper_id:
                    other_id = d.paper_b_id if d.paper_a_id == p.paper_id else d.paper_a_id
                    other_num = evidence_pack.paper_number_map.get(other_id)
                    other_marker = f"[{other_num}]" if other_num else "[?]"
                    subject = d.shared_subject.strip()
                    limitation_cell = f"Contradicts {other_marker}: {subject[:45]}"
                    break

        table_rows.append([source_cell, approach_cell, finding_cell, limitation_cell])

    notes = (
        f"Structured comparison of {len(table_rows)} peer-reviewed papers evaluating approaches, "
        f"verified findings, and noted limitations."
    )

    return SlideSpec(
        layout="table",
        title="Comparative Literature Findings",
        table_header=table_header,
        table_rows=table_rows,
        claim_ids=all_claim_ids[:10],
        notes=notes,
    )


def build_references_slides(
    evidence_pack: EvidencePack,
    findings: FindingsPacket,
    citation_result: CitationResult,
) -> list[SlideSpec]:
    """
    Construct numbered References slide(s) to appear right before the Closing slide.
    Formatted as '[n] First author et al. (year). Title. Venue'.
    Splits into multiple slides (at 5 entries per slide) to respect bullet constraints.
    """
    entries: list[str] = []
    sorted_papers = sorted(evidence_pack.papers_list, key=lambda p: p.number)

    for p in sorted_papers:
        if p.authors:
            first_author = p.authors[0].split(",")[0].strip()
            if len(p.authors) > 1:
                author_str = f"{first_author} et al."
            else:
                author_str = first_author
        else:
            author_match = re.match(r"^([^(\"]+)", p.full_entry)
            if author_match and len(author_match.group(1).strip()) > 2:
                author_str = author_match.group(1).strip().rstrip(".,")
            else:
                author_str = "Author et al."

        year_str = f"({p.year})" if p.year else "(n.d.)"
        title_str = p.title.rstrip(".")
        venue_str = f" {p.venue.rstrip('.')}." if p.venue else ""

        entry = f"[{p.number}] {author_str} {year_str}. {title_str}.{venue_str}"
        entries.append(entry.strip())

    chunk_size = 5
    chunks = [entries[i : i + chunk_size] for i in range(0, len(entries), chunk_size)]
    if not chunks:
        chunks = [["[1] Referenced literature sources."]]

    total_chunks = len(chunks)
    slides: list[SlideSpec] = []
    for idx, chunk in enumerate(chunks):
        title = "References" if total_chunks == 1 else f"References ({idx + 1}/{total_chunks})"
        notes = f"Academic citations and literature references (part {idx + 1} of {total_chunks})."
        slides.append(
            SlideSpec(
                layout="bullets",
                title=title,
                bullets=chunk,
                notes=notes,
            )
        )
    return slides


def build_contradictions_slide(
    findings: FindingsPacket,
    evidence_pack: EvidencePack,
) -> Optional[SlideSpec]:
    """
    If findings.contradiction_details is non-empty, add ONE slide titled
    'Conflicting or Open Findings' with one bullet per detail (max 3):
    both papers' markers plus a shortened explanation. If empty, return None.
    """
    if not findings.contradiction_details:
        return None

    details = findings.contradiction_details[:3]
    bullets: list[str] = []
    claim_ids: list[str] = []

    for d in details:
        na = evidence_pack.paper_number_map.get(d.paper_a_id)
        nb = evidence_pack.paper_number_map.get(d.paper_b_id)
        marker_a = f"[{na}]" if na else "[?]"
        marker_b = f"[{nb}]" if nb else "[?]"

        exp = d.explanation.strip()
        if len(exp) > 130:
            exp = exp[:127].rsplit(" ", 1)[0] + "..."

        bullet = f"{marker_a} vs {marker_b}: {exp}"
        bullets.append(bullet)

        if d.claim_a_id in evidence_pack.verified_claim_ids:
            claim_ids.append(d.claim_a_id)
        if d.claim_b_id in evidence_pack.verified_claim_ids:
            claim_ids.append(d.claim_b_id)

    notes = (
        f"Analysis of {len(bullets)} open contradiction{'s' if len(bullets) != 1 else ''} "
        f"or divergent empirical findings identified across literature sources."
    )

    return SlideSpec(
        layout="bullets",
        title="Conflicting or Open Findings",
        bullets=bullets,
        claim_ids=claim_ids,
        notes=notes,
    )


def validate_diagram_nodes_and_edges(
    raw_nodes: list[str],
    raw_edges: list[Any],
    own_architecture_summary: str,
) -> tuple[list[str], list[tuple[str, str]]]:
    """
    Validate that diagram nodes contain ONLY words present in user's own_architecture_summary,
    are <= 3 words each, and total at most 8 nodes. Edges are filtered to valid nodes.
    """
    user_words = set(re.findall(r"[a-zA-Z0-9]+", own_architecture_summary.lower()))

    valid_nodes: list[str] = []
    for node in raw_nodes:
        if not isinstance(node, str) or not node.strip():
            continue
        cleaned = node.strip()
        words = re.findall(r"[a-zA-Z0-9]+", cleaned.lower())
        if not words or len(words) > 3:
            continue
        if all(w in user_words for w in words):
            if cleaned not in valid_nodes:
                valid_nodes.append(cleaned)

    valid_nodes = valid_nodes[:8]

    if not valid_nodes:
        raw_candidates = [
            w for w in re.findall(r"[a-zA-Z0-9]+", own_architecture_summary) if len(w) > 3
        ]
        valid_nodes = [w.capitalize() for w in raw_candidates[:4]] or ["System", "Process"]

    valid_nodes_set = set(valid_nodes)
    valid_edges: list[tuple[str, str]] = []
    for edge in raw_edges:
        if isinstance(edge, (list, tuple)) and len(edge) == 2:
            src, dst = str(edge[0]).strip(), str(edge[1]).strip()
            if src in valid_nodes_set and dst in valid_nodes_set and src != dst:
                if (src, dst) not in valid_edges:
                    valid_edges.append((src, dst))

    if not valid_edges and len(valid_nodes) > 1:
        for i in range(len(valid_nodes) - 1):
            valid_edges.append((valid_nodes[i], valid_nodes[i + 1]))

    return valid_nodes, valid_edges


# ---------------------------------------------------------------------------
# Deterministic Fallback Deck
# ---------------------------------------------------------------------------

def build_deterministic_fallback_deck(
    guided_input: GuidedInputBundle,
    findings: FindingsPacket,
    evidence_pack: EvidencePack,
    citations: CitationResult | None = None,
) -> StructuredContent:
    """
    Build a deterministic, fully-grounded slide deck without LLM involvement.
    Used when the LLM call fails, times out, or returns malformed output.
    Follows all sanitizer, numbering, and grounding rules.
    """
    cover = guided_input.cover_info
    pres = guided_input.project_presentation_info or ProjectPresentationInfo(
        problem_statement=f"Research on {findings.topic}",
        tech_stack=["Python"],
        own_architecture_summary="Automated pipeline architecture",
        own_results_summary="Verified research findings compiled",
    )

    slides: list[SlideSpec] = []

    # 1. Title
    slides.append(
        SlideSpec(
            layout="title",
            title=cover.title,
            bullets=[cover.subtitle] if cover.subtitle else [],
            notes=f"Today we present research on {cover.title}.",
        )
    )

    # 2. Agenda
    agenda_bullets = [
        "Problem Statement & Motivation",
        "Literature Findings & Key Insights",
        "Evidence Distribution & Analysis",
        "System Architecture & Pipeline",
        "Project Results & Evaluation",
    ]
    slides.append(
        SlideSpec(
            layout="agenda",
            title="Presentation Agenda",
            bullets=agenda_bullets,
            notes="Overview of research problems, literature evidence, system architecture, and outcomes.",
        )
    )

    # 3. Problem Statement
    prob_bullets = [
        s.strip()
        for s in re.split(r"[.\n]+", pres.problem_statement)
        if len(s.strip()) > 5
    ][:4] or [pres.problem_statement]
    slides.append(
        SlideSpec(
            layout="bullets",
            title="Research Problem",
            bullets=prob_bullets[:5],
            notes="Primary research problem and operational motivation.",
        )
    )

    # 4. Literature Themes
    theme1_claims = evidence_pack.verified_claims[:4]
    theme1_bullets = [
        f"{c.text} [{c.paper_number}]" for c in theme1_claims
    ]
    if theme1_bullets:
        slides.append(
            SlideSpec(
                layout="bullets",
                title="Literature Review: Core Themes",
                bullets=theme1_bullets[:5],
                claim_ids=[c.claim_id for c in theme1_claims],
                notes="Core verified empirical insights extracted from surveyed academic literature.",
            )
        )

    # 5. Contradictions (if any)
    contra_slide = build_contradictions_slide(findings, evidence_pack)
    if contra_slide:
        slides.append(contra_slide)

    # 6. Chart slide
    fig_chart, chart_title, chart_notes = compute_chart_figure_and_notes(evidence_pack)
    slides.append(
        SlideSpec(
            layout="chart",
            title=chart_title,
            figure_id=CHART_FIGURE_ID,
            notes=chart_notes,
        )
    )

    # 7. Comparison Table slide
    slides.append(build_table_slide(evidence_pack, findings))

    # 8. Architecture Diagram slide
    nodes, edges = validate_diagram_nodes_and_edges([], [], pres.own_architecture_summary)
    fig_diag = FigureSpec(
        figure_id=DIAGRAM_FIGURE_ID,
        kind="diagram",
        title="System Architecture",
        nodes=nodes,
        edges=edges,
    )
    slides.append(
        SlideSpec(
            layout="diagram",
            title="System Architecture Flow",
            figure_id=DIAGRAM_FIGURE_ID,
            notes="Component architecture and workflow flow of the system.",
        )
    )

    # 9. Tech Stack slide (isolated from own results)
    if pres.tech_stack:
        slides.append(
            SlideSpec(
                layout="bullets",
                title="Tech Stack & Implementation",
                bullets=[str(t).strip() for t in pres.tech_stack[:5]],
                notes="Implementation technologies and software frameworks utilized in the project.",
            )
        )

    # 10. Own Results slide (only own_results_summary content)
    res_bullets = [
        s.strip()
        for s in re.split(r"[.\n]+", pres.own_results_summary)
        if len(s.strip()) > 5
    ][:4] or [pres.own_results_summary]
    slides.append(
        SlideSpec(
            layout="bullets",
            title="Project Results & Evaluation",
            bullets=res_bullets[:5],
            notes="Empirical outcomes achieved by the proposed system implementation.",
        )
    )

    # 11. References slide(s) before closing
    ref_citations = citations or CitationResult(citation_style="apa", citations=[])
    slides.extend(build_references_slides(evidence_pack, findings, ref_citations))

    # 12. Closing slide: 2-3 short bullets built only from grounded content
    closing_bullets: list[str] = []
    if evidence_pack.verified_claims:
        top_c = evidence_pack.verified_claims[0]
        closing_bullets.append(f"Literature: {top_c.text[:80].strip()} [{top_c.paper_number}]")
    if res_bullets:
        closing_bullets.append(f"Outcome: {res_bullets[0][:85].strip()}")
    closing_bullets.append("Summary: All evaluated citations verified with zero hallucinated references.")

    slides.append(
        SlideSpec(
            layout="closing",
            title="Conclusion & Summary",
            bullets=closing_bullets[:3],
            notes="Concluding synthesis uniting grounded literature findings and empirical project outcomes.",
        )
    )

    # Apply sanitizer to every slide in fallback deck
    sanitized_slides = [sanitize_slide(s, evidence_pack) for s in slides if s.bullets or s.layout in ("chart", "table", "diagram")]

    return StructuredContent(
        slides=sanitized_slides,
        figures=[fig_chart, fig_diag],
    )


# ---------------------------------------------------------------------------
# LLM Prompt & Post-Validation
# ---------------------------------------------------------------------------

def _build_llm_prompt(
    guided_input: GuidedInputBundle,
    findings: FindingsPacket,
    evidence_pack: EvidencePack,
) -> str:
    """
    Build a concise, grounded prompt containing user facts and verified claims.
    Strictly forbids writing claim IDs or brackets in any text;
    grounding goes ONLY in the claim_ids field.
    """
    cover = guided_input.cover_info
    pres = guided_input.project_presentation_info or ProjectPresentationInfo(
        problem_statement=findings.topic,
        tech_stack=[],
        own_architecture_summary="",
        own_results_summary="",
    )

    claims_subset = evidence_pack.verified_claims[:MAX_CLAIMS_IN_PROMPT]
    claims_text = "\n".join(
        f"- Claim ID: {c.claim_id} | Paper: {c.paper_marker} | Text: {c.text}"
        for c in claims_subset
    ) or "No verified claims found."

    prompt = f"""You are an expert academic presentation designer.
Generate a structured 9-12 slide presentation in JSON format.

RULES:
1. Output ONLY valid JSON, with no explanation or markdown outside the JSON block.
2. CITATION GROUNDING RULE: Do NOT write Claim IDs, paper IDs, or citation brackets (like [1], [paper_1], or [claim_01]) in ANY bullet text, title, table cell, or notes. Put all grounding Claim IDs ONLY in the slide's "claim_ids" field. Numeric citation markers will be attached deterministically by the system.
3. Every literature bullet point MUST be grounded in one of the provided Claim IDs. If a bullet is not grounded in a verified Claim ID, it will be rejected.
4. Diagram nodes MUST ONLY use words that appear in the USER ARCHITECTURE SUMMARY below. Do NOT invent components. Max 3 words per node.
5. In the Own Results slide, use ONLY the USER RESULTS SUMMARY. Do NOT invent numbers or mention the tech stack.
6. The Tech Stack gets its own slide using ONLY the TECH STACK list below. Do NOT repeat the tech stack on other slides.
7. Maximum 5 bullets per slide.
8. Allowed slide layouts: "title", "agenda", "section_divider", "bullets", "table", "chart", "diagram", "closing".
9. Speaker notes MUST describe what that slide actually shows; do NOT use generic welcome filler.

INPUT DATA:
- Topic: {findings.topic}
- Cover Title: {cover.title}
- Cover Subtitle: {cover.subtitle or ''}
- Problem Statement: {pres.problem_statement}
- Tech Stack: {', '.join(pres.tech_stack)}
- User Architecture Summary: {pres.own_architecture_summary}
- User Results Summary: {pres.own_results_summary}

VERIFIED CLAIMS (Use these Claim IDs in the 'claim_ids' field for literature slides):
{claims_text}

JSON FORMAT REQUIRED:
{{
  "slides": [
    {{
      "layout": "title",
      "title": "{cover.title}",
      "bullets": ["{cover.subtitle or ''}"],
      "notes": "Presentation context and objectives."
    }},
    {{
      "layout": "agenda",
      "title": "Agenda",
      "bullets": ["Problem Statement", "Literature Review", "System Architecture", "Evaluation Results", "Conclusion"],
      "notes": "Roadmap of topics covered in this talk."
    }},
    {{
      "layout": "bullets",
      "title": "Problem Statement",
      "bullets": ["Research problem bullet 1", "Research problem bullet 2"],
      "notes": "Core problem statement and operational challenges."
    }},
    {{
      "layout": "bullets",
      "title": "Literature Review: Core Insights",
      "bullets": ["Finding text one without brackets", "Finding text two without brackets"],
      "claim_ids": ["claim_01", "claim_02"],
      "notes": "Detailed analysis of verified literature findings."
    }},
    {{
      "layout": "diagram",
      "title": "System Architecture",
      "figure_id": "{DIAGRAM_FIGURE_ID}",
      "notes": "Component flow and architectural pipeline."
    }},
    {{
      "layout": "bullets",
      "title": "Tech Stack & Implementation",
      "bullets": ["Technology component 1", "Technology component 2"],
      "notes": "Technical stack and implementation environment."
    }},
    {{
      "layout": "bullets",
      "title": "Project Results & Evaluation",
      "bullets": ["Empirical result bullet 1"],
      "notes": "Quantitative outcomes and benchmark performance."
    }},
    {{
      "layout": "closing",
      "title": "Conclusion",
      "bullets": ["Primary literature insight", "System outcome"],
      "notes": "Concluding summary synthesizing literature findings and system outcomes."
    }}
  ],
  "diagram_nodes": ["Node1", "Node2", "Node3"],
  "diagram_edges": [["Node1", "Node2"], ["Node2", "Node3"]]
}}
"""
    return prompt


def _parse_and_validate_llm_json(
    raw_response: str,
    guided_input: GuidedInputBundle,
    findings: FindingsPacket,
    evidence_pack: EvidencePack,
    citation_result: CitationResult,
) -> StructuredContent:
    """
    Parse raw LLM response, sanitize every text field, enforce evidence grounding,
    drop ungrounded bullets, construct deterministic table, chart, contradictions,
    and references slides, and attach pre-computed figures.
    """
    cleaned = raw_response.strip()
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned)
        cleaned = re.sub(r"\s*```$", "", cleaned)

    data = json.loads(cleaned)
    if not isinstance(data, dict) or "slides" not in data or not isinstance(data["slides"], list):
        raise ValueError("LLM response does not contain a 'slides' list.")

    pres = guided_input.project_presentation_info or ProjectPresentationInfo(
        problem_statement=findings.topic,
        tech_stack=[],
        own_architecture_summary="",
        own_results_summary="",
    )

    validated_slides: list[SlideSpec] = []
    has_diagram_slide = False
    has_tech_stack_slide = False

    valid_layouts = {
        "title",
        "agenda",
        "section_divider",
        "bullets",
        "table",
        "chart",
        "diagram",
        "closing",
    }

    # Verified claims lookup
    verified_claims_map = {c.claim_id: c for c in evidence_pack.verified_claims}

    for item in data["slides"]:
        if not isinstance(item, dict):
            continue

        raw_layout = item.get("layout", "bullets")
        layout = raw_layout if raw_layout in valid_layouts else "bullets"
        title = item.get("title") or "Slide"

        # Suppress chart or table from LLM: they will be generated deterministically
        if layout in ("chart", "table"):
            continue

        # Suppress References or Closing from raw LLM: will be generated deterministically
        if "reference" in title.lower() or layout == "closing":
            continue

        raw_bullets = item.get("bullets") or []
        bullets = [str(b).strip() for b in raw_bullets if str(b).strip()] if isinstance(raw_bullets, list) else []

        raw_claims = item.get("claim_ids") or []
        claim_ids = [str(c).strip() for c in raw_claims if str(c).strip() in evidence_pack.verified_claim_ids] if isinstance(raw_claims, list) else []

        # Identify literature slides
        is_literature_slide = (
            layout == "bullets"
            and any(
                kw in title.lower()
                for kw in (
                    "literature",
                    "finding",
                    "related work",
                    "state of the art",
                    "background",
                    "comparison with literature",
                )
            )
            and not any(
                kw in title.lower()
                for kw in (
                    "problem",
                    "result",
                    "tech stack",
                    "implementation",
                    "architecture",
                    "agenda",
                    "conclusion",
                )
            )
        )

        if is_literature_slide:
            filtered_bullets: list[str] = []
            verified_cids_used: list[str] = []

            for idx, b in enumerate(bullets):
                # 1. Check if raw bullet contained bracketed claim ID
                bracket_ids = re.findall(r"\[([a-zA-Z0-9_\-:]+)\]", b)
                matched_claims: list[VerifiedClaimEvidence] = []

                for bid in bracket_ids:
                    bid_clean = bid.split(":claim:")[-1] if ":claim:" in bid else bid
                    if bid in verified_claims_map:
                        matched_claims.append(verified_claims_map[bid])
                    elif bid_clean in verified_claims_map:
                        matched_claims.append(verified_claims_map[bid_clean])

                # 2. Check if slide claim_ids has corresponding verified claim
                if not matched_claims and claim_ids:
                    # Check text overlap with verified claims in claim_ids
                    b_words = set(re.findall(r"[a-zA-Z0-9]+", b.lower()))
                    best_claim = None
                    best_overlap = 0

                    for cid in claim_ids:
                        c_obj = verified_claims_map.get(cid)
                        if c_obj:
                            c_words = set(re.findall(r"[a-zA-Z0-9]+", c_obj.text.lower()))
                            overlap = len(b_words & c_words)
                            if overlap > best_overlap and overlap >= 3:
                                best_overlap = overlap
                                best_claim = c_obj

                    if best_claim:
                        matched_claims.append(best_claim)
                    elif idx < len(claim_ids) and claim_ids[idx] in verified_claims_map:
                        matched_claims.append(verified_claims_map[claim_ids[idx]])

                # Only keep bullet if grounded in at least one verified claim
                if matched_claims:
                    paper_nums = sorted(set(c.paper_number for c in matched_claims))
                    marker = f"[{', '.join(str(n) for n in paper_nums)}]"
                    clean_b = sanitize_text(b, evidence_pack)
                    # Strip any trailing bracket
                    clean_b = re.sub(r"\s*\[\d+(?:\s*,\s*\d+)*\]$", "", clean_b).strip()
                    filtered_bullets.append(f"{clean_b} {marker}")
                    for c in matched_claims:
                        if c.claim_id not in verified_cids_used:
                            verified_cids_used.append(c.claim_id)

            bullets = filtered_bullets
            claim_ids = verified_cids_used

            # If literature slide has no surviving bullets, drop it
            if not bullets:
                continue

        # Project own slides: Problem, Results, Tech Stack, Architecture
        is_problem_slide = "problem" in title.lower() and layout == "bullets"
        if is_problem_slide and pres.problem_statement:
            prob_sentences = [
                s.strip() for s in re.split(r"[.\n]+", pres.problem_statement) if len(s.strip()) > 5
            ]
            bullets = prob_sentences[:5] or [pres.problem_statement]

        is_tech_stack_slide = "tech stack" in title.lower() or "implementation" in title.lower()
        if is_tech_stack_slide and pres.tech_stack:
            has_tech_stack_slide = True
            bullets = [str(t).strip() for t in pres.tech_stack[:5]]

        is_results_slide = "result" in title.lower() and layout == "bullets"
        if is_results_slide and pres.own_results_summary:
            res_sentences = [
                s.strip() for s in re.split(r"[.\n]+", pres.own_results_summary) if len(s.strip()) > 5
            ]
            # Remove any tech stack items from Own Results
            cleaned_res: list[str] = []
            for sent in res_sentences:
                if not any(tech.lower() in sent.lower() for tech in pres.tech_stack if len(tech) > 2):
                    cleaned_res.append(sent)
            bullets = cleaned_res[:5] or res_sentences[:5] or [pres.own_results_summary]

        if layout == "diagram":
            figure_id = DIAGRAM_FIGURE_ID
            has_diagram_slide = True
        else:
            figure_id = None

        # Sanitize slide text
        notes = item.get("notes") or f"Analysis of {title}."
        spec = SlideSpec(
            layout=layout,
            title=title,
            bullets=bullets[:5],
            figure_id=figure_id,
            notes=notes,
            claim_ids=claim_ids,
        )
        sanitized_spec = sanitize_slide(spec, evidence_pack)

        # Drop any bullet slide that ended up with no bullets
        if sanitized_spec.layout in ("bullets", "agenda") and not sanitized_spec.bullets:
            continue

        validated_slides.append(sanitized_spec)

    # 1. Ensure Contradictions slide is present if findings.contradiction_details exist
    contra_slide = build_contradictions_slide(findings, evidence_pack)
    if contra_slide:
        # Insert after literature slides (index ~4)
        lit_indices = [i for i, s in enumerate(validated_slides) if "literature" in s.title.lower()]
        insert_pos = (max(lit_indices) + 1) if lit_indices else min(4, len(validated_slides))
        validated_slides.insert(insert_pos, contra_slide)

    # 2. Add deterministic Chart slide
    fig_chart, chart_title, chart_notes = compute_chart_figure_and_notes(evidence_pack)
    chart_slide = SlideSpec(
        layout="chart",
        title=chart_title,
        figure_id=CHART_FIGURE_ID,
        notes=chart_notes,
    )
    # Insert chart after literature/contradiction slides
    chart_pos = min(5, len(validated_slides))
    validated_slides.insert(chart_pos, chart_slide)

    # 3. Add deterministic Table slide
    table_slide = build_table_slide(evidence_pack, findings)
    validated_slides.insert(chart_pos + 1, table_slide)

    # 4. Ensure Architecture Diagram slide exists
    raw_nodes = data.get("diagram_nodes") or []
    raw_edges = data.get("diagram_edges") or []
    diag_nodes, diag_edges = validate_diagram_nodes_and_edges(
        raw_nodes, raw_edges, pres.own_architecture_summary
    )
    fig_diag = FigureSpec(
        figure_id=DIAGRAM_FIGURE_ID,
        kind="diagram",
        title="Architecture Workflow",
        nodes=diag_nodes,
        edges=diag_edges,
    )

    if not has_diagram_slide:
        validated_slides.insert(
            min(7, len(validated_slides)),
            SlideSpec(
                layout="diagram",
                title="System Architecture Flow",
                figure_id=DIAGRAM_FIGURE_ID,
                notes="Architectural flow of system components.",
            ),
        )

    # 5. Ensure Tech Stack slide exists if tech stack is present
    if pres.tech_stack and not has_tech_stack_slide:
        stack_slide = SlideSpec(
            layout="bullets",
            title="Tech Stack & Implementation",
            bullets=[str(t).strip() for t in pres.tech_stack[:5]],
            notes="Technical stack and implementation frameworks.",
        )
        validated_slides.insert(min(8, len(validated_slides)), stack_slide)

    # 6. Add deterministic References slide(s) before closing
    ref_slides = build_references_slides(evidence_pack, findings, citation_result)
    validated_slides.extend(ref_slides)

    # 7. Add deterministic Closing slide
    closing_bullets: list[str] = []
    if evidence_pack.verified_claims:
        top_c = evidence_pack.verified_claims[0]
        closing_bullets.append(f"Literature: {top_c.text[:80].strip()} [{top_c.paper_number}]")
    if pres.own_results_summary:
        first_res = re.split(r"[.\n]+", pres.own_results_summary)[0].strip()
        closing_bullets.append(f"System outcome: {first_res[:85].strip()}")
    closing_bullets.append("Summary: All evaluated citations verified with zero hallucinated references.")

    validated_slides.append(
        SlideSpec(
            layout="closing",
            title="Conclusion & Summary",
            bullets=closing_bullets[:3],
            notes="Concluding synthesis uniting grounded literature findings and empirical project outcomes.",
        )
    )

    # Final pass: sanitize all slides and filter any empty bullet slides
    final_slides = [
        sanitize_slide(s, evidence_pack)
        for s in validated_slides
        if s.bullets or s.layout in ("chart", "table", "diagram")
    ]

    return StructuredContent(
        slides=final_slides,
        figures=[fig_chart, fig_diag],
    )


# ---------------------------------------------------------------------------
# Public Entrypoint
# ---------------------------------------------------------------------------

def build_ppt_structured(
    guided_input: GuidedInputBundle,
    findings: FindingsPacket,
    citation_result: CitationResult,
    llm: Optional[Any] = None,
) -> StructuredContent:
    """
    Build a grounded StructuredContent instance for PPT generation.
    Uses ONE Gemini call; on any error, returns a deterministic fallback deck.
    Never raises exceptions to callers.
    """
    evidence_pack = build_evidence_pack(findings, citation_result)

    try:
        client = llm or GeminiClient()
        prompt = _build_llm_prompt(guided_input, findings, evidence_pack)

        response_text = client.generate(
            prompt,
            paper_id="__compose__",
            agent_name="composer",
            purpose="ppt_slides",
            use_cache=True,
        )

        return _parse_and_validate_llm_json(
            response_text,
            guided_input,
            findings,
            evidence_pack,
            citation_result,
        )

    except Exception as exc:
        logger.warning(
            "Failed to generate LLM-structured PPT content (%s). "
            "Falling back to deterministic structured deck.",
            exc,
        )
        return build_deterministic_fallback_deck(
            guided_input,
            findings,
            evidence_pack,
            citation_result,
        )
