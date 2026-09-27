"""
Shared Gemini API client with caching, logging, and token-usage discipline.

Design goals (per Person B role brief - "Token / API Usage Discipline"):
- Every LLM response is cached by (paper_id, agent_name, prompt_hash) so
  re-running the same paper during dev/testing never re-triggers a paid
  or quota-consuming call.
- Every real call is logged (agent name, approx tokens, purpose) so the
  team can see usage patterns before the demo.
- Callers are responsible for truncating/chunking inputs before calling
  here (never paste a whole paper in) - this module does not do that.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import time
from pathlib import Path
from typing import Optional

logger = logging.getLogger("research_assistant.llm")
if not logger.handlers:
    logging.basicConfig(level=logging.INFO)

CACHE_DIR = Path(os.environ.get("RA_CACHE_DIR", ".cache/llm"))
CACHE_DIR.mkdir(parents=True, exist_ok=True)

GEMINI_MODEL = os.environ.get("GEMINI_MODEL", "gemini-3.8-flash")


def _prompt_hash(prompt: str) -> str:
    return hashlib.sha256(prompt.encode("utf-8")).hexdigest()[:16]


def _cache_path(paper_id: str, agent_name: str, prompt_hash: str) -> Path:
    safe_paper_id = paper_id.replace("/", "_").replace(":", "_")
    return CACHE_DIR / f"{safe_paper_id}__{agent_name}__{prompt_hash}.json"


def _read_cache(paper_id: str, agent_name: str, prompt: str) -> Optional[str]:
    path = _cache_path(paper_id, agent_name, _prompt_hash(prompt))
    if path.exists():
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            logger.info("[cache HIT] agent=%s paper_id=%s", agent_name, paper_id)
            return data.get("response")
        except (json.JSONDecodeError, OSError):
            return None
    return None


def _write_cache(paper_id: str, agent_name: str, prompt: str, response: str) -> None:
    path = _cache_path(paper_id, agent_name, _prompt_hash(prompt))
    try:
        path.write_text(json.dumps({"prompt": prompt, "response": response}), encoding="utf-8")
    except OSError as exc:
        logger.warning("Failed to write LLM cache: %s", exc)


class GeminiClient:
    """
    Thin wrapper around the Gemini API.

    The google-generativeai SDK import is deferred to the first real
    (cache-miss) call, so this module can be imported - and cache-hit /
    offline-tested code paths can run - even without the SDK installed.
    """

    def __init__(self, api_key: Optional[str] = None, model: str = GEMINI_MODEL):
        self.api_key = api_key or os.environ.get("GEMINI_API_KEY")
        self.model_name = model
        self._model = None

    def _ensure_model(self):
        if self._model is not None:
            return self._model
        if not self.api_key:
            raise RuntimeError(
                "GEMINI_API_KEY is not set. Export it in your environment "
                "before making a live Gemini call."
            )
        import google.generativeai as genai  # deferred import

        genai.configure(api_key=self.api_key)
        self._model = genai.GenerativeModel(self.model_name)
        return self._model

    def generate(
        self,
        prompt: str,
        *,
        paper_id: str,
        agent_name: str,
        purpose: str,
        use_cache: bool = True,
    ) -> str:
        """Call Gemini, transparently caching by (paper_id, agent_name, prompt_hash)."""
        if use_cache:
            cached = _read_cache(paper_id, agent_name, prompt)
            if cached is not None:
                return cached

        model = self._ensure_model()
        start = time.time()
        result = model.generate_content(prompt)
        elapsed = time.time() - start

        text = (result.text or "").strip()

        approx_tokens = len(prompt.split()) + len(text.split())
        logger.info(
            "[LLM CALL] agent=%s paper_id=%s purpose=%s approx_tokens~%d elapsed=%.2fs",
            agent_name, paper_id, purpose, approx_tokens, elapsed,
        )

        if use_cache:
            _write_cache(paper_id, agent_name, prompt, text)

        return text
