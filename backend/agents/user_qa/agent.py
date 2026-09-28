"""
User Q&A Agent.

Always-on, retrieval-grounded question-answering agent for user queries.
Answers questions grounded strictly in the ingested research paper chunks.
"""
from __future__ import annotations

import hashlib
import logging
from typing import Any, Callable, Optional

from backend.agents.common.llm_client import GeminiClient
from backend.schemas.schemas import UserQARequest, UserQAResponse
from backend.vectorstore.store import search_similar_chunks

logger = logging.getLogger("research_assistant.user_qa")
if not logger.handlers:
    logging.basicConfig(level=logging.INFO)

AGENT_NAME = "user_qa_agent"
NOT_ENOUGH_INFO_ANSWER = (
    "The ingested research papers do not contain enough information to answer this question."
)


def _make_qa_cache_key(question: str) -> str:
    """Generate a filesystem-safe, deterministic cache key from the question."""
    return f"qa_{hashlib.sha256(question.strip().lower().encode('utf-8')).hexdigest()[:16]}"


def _parse_search_results(results: Any) -> list[dict[str, Any]]:
    """
    Parse raw ChromaDB results dictionary or list into a list of chunk dicts:
    [{'text': str, 'paper_id': Optional[str], 'metadata': dict}, ...]
    """
    if not results:
        return []

    raw_docs: list[Any] = []
    raw_metas: list[Any] = []

    if isinstance(results, dict):
        docs_val = results.get("documents")
        metas_val = results.get("metadatas")

        if docs_val and isinstance(docs_val, list):
            # ChromaDB returns a 2D list: [[doc1, doc2, ...]]
            if len(docs_val) > 0 and isinstance(docs_val[0], list):
                raw_docs = docs_val[0]
            else:
                raw_docs = docs_val

        if metas_val and isinstance(metas_val, list):
            # ChromaDB returns a 2D list: [[meta1, meta2, ...]]
            if len(metas_val) > 0 and isinstance(metas_val[0], list):
                raw_metas = metas_val[0]
            else:
                raw_metas = metas_val
    elif isinstance(results, list):
        raw_docs = results
        raw_metas = []

    parsed_chunks: list[dict[str, Any]] = []
    for i, doc in enumerate(raw_docs):
        if doc is None:
            continue
        text = str(doc).strip()
        if not text:
            continue

        meta = (
            raw_metas[i]
            if i < len(raw_metas) and isinstance(raw_metas[i], dict)
            else {}
        )
        paper_id = meta.get("paper_id")

        parsed_chunks.append({
            "text": text,
            "paper_id": str(paper_id).strip() if paper_id else None,
            "metadata": meta,
        })

    return parsed_chunks


class UserQAAgent:
    """Agent that performs grounded Q&A over ingested paper chunks."""

    def __init__(self, client: Optional[GeminiClient] = None):
        self.client = client or GeminiClient()

    def answer_question(
        self,
        request: UserQARequest,
        allowed_paper_ids: Optional[set[str]] = None,
        top_k: int = 5,
        search_fn: Optional[Callable[..., Any]] = None,
    ) -> UserQAResponse:
        """
        Answer a user question grounded strictly in retrieved chunks.

        1. Retrieve top chunks with search_fn (default: search_similar_chunks).
        2. Filter by allowed_paper_ids if provided.
        3. If no relevant chunks remain, return 'not enough info' response without calling LLM.
        4. Call Gemini using only the retrieved chunk texts.
        5. Return answer with deduplicated source_paper_ids of chunks actually used.
        """
        search = search_fn or search_similar_chunks

        try:
            results = search(request.question, top_k=top_k)
        except Exception as exc:
            logger.exception("[%s] Vector store search failed: %s", AGENT_NAME, exc)
            return UserQAResponse(
                answer=f"Error retrieving relevant research papers: {exc}",
                source_paper_ids=[],
            )

        parsed_chunks = _parse_search_results(results)

        # Filter by allowed_paper_ids if provided
        chunks_kept: list[dict[str, Any]] = []
        for chunk in parsed_chunks:
            pid = chunk.get("paper_id")
            if allowed_paper_ids is not None:
                if not pid or pid not in allowed_paper_ids:
                    continue
            chunks_kept.append(chunk)

        if top_k and len(chunks_kept) > top_k:
            chunks_kept = chunks_kept[:top_k]

        # Guardrail: If no relevant chunks remain, do not call Gemini.
        if not chunks_kept:
            logger.info(
                "[%s] No relevant chunks found for question: %s",
                AGENT_NAME,
                request.question,
            )
            return UserQAResponse(
                answer=NOT_ENOUGH_INFO_ANSWER,
                source_paper_ids=[],
            )

        # Deduplicate paper_ids preserving order of appearance
        used_paper_ids: list[str] = []
        seen_pids: set[str] = set()
        for chunk in chunks_kept:
            pid = chunk.get("paper_id")
            if pid and pid not in seen_pids:
                seen_pids.add(pid)
                used_paper_ids.append(pid)

        # Build prompt containing only the retrieved chunk texts
        excerpts: list[str] = []
        for i, chunk in enumerate(chunks_kept, start=1):
            pid = chunk.get("paper_id")
            tag = f"Excerpt from paper {pid}" if pid else f"Excerpt {i}"
            excerpts.append(f"[{tag}]\n{chunk['text']}")

        context = "\n\n".join(excerpts)

        prompt = (
            "You are an AI research assistant answering a user's question based strictly on excerpts from ingested research papers.\n\n"
            f"Excerpts:\n{context}\n\n"
            f"Question: {request.question}\n\n"
            "Instructions:\n"
            "Answer the question using ONLY the provided excerpts above. Do not use outside knowledge or speculate. "
            "If the excerpts do not contain sufficient details to fully answer the question, state that the ingested papers do not contain enough information.\n\n"
            "Answer:"
        )

        cache_key = _make_qa_cache_key(request.question)

        try:
            raw_answer = self.client.generate(
                prompt,
                paper_id=cache_key,
                agent_name=AGENT_NAME,
                purpose="user_qa_answer",
                use_cache=True,
            )
            answer = (raw_answer or "").strip()
            if not answer:
                answer = NOT_ENOUGH_INFO_ANSWER
        except Exception as exc:
            logger.exception("[%s] LLM generation failed for question: %s: %s", AGENT_NAME, request.question, exc)
            return UserQAResponse(
                answer=f"Error generating answer: {exc}",
                source_paper_ids=[],
            )

        return UserQAResponse(
            answer=answer,
            source_paper_ids=used_paper_ids,
        )


def run_user_qa(
    request: UserQARequest,
    allowed_paper_ids: Optional[set[str]] = None,
    client: Optional[GeminiClient] = None,
    top_k: int = 5,
    search_fn: Optional[Callable[..., Any]] = None,
) -> UserQAResponse:
    """
    Entry point for the User Q&A Agent.

    :param request: UserQARequest containing the question and topic.
    :param allowed_paper_ids: Optional set of allowed paper IDs to filter retrieved chunks.
    :param client: Optional injectable GeminiClient (for testing/mocking).
    :param top_k: Maximum number of chunks to retrieve (default 5).
    :param search_fn: Optional custom/mock retrieval function.
    :return: UserQAResponse with answer and deduplicated source_paper_ids.
    """
    agent = UserQAAgent(client=client)
    return agent.answer_question(
        request=request,
        allowed_paper_ids=allowed_paper_ids,
        top_k=top_k,
        search_fn=search_fn,
    )
