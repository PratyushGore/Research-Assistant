/**
 * API client module for Multi-Agent AI Research & Publication Assistant.
 * All backend HTTP and WebSocket communication is centralized here.
 */

export const API_BASE = "http://localhost:8000";

const WS_BASE = API_BASE.replace(/^http/, "ws");

export const getResearchWsUrl = (sessionId) => {
  return `${WS_BASE}/ws/research/${sessionId}`;
};

export const getDownloadUrl = (downloadUrl) => {
  if (!downloadUrl) return "";
  if (downloadUrl.startsWith("http://") || downloadUrl.startsWith("https://")) {
    return downloadUrl;
  }
  return `${API_BASE}${downloadUrl.startsWith("/") ? "" : "/"}${downloadUrl}`;
};

/**
 * Parses and returns the response body or throws a descriptive error.
 */
async function handleResponse(response) {
  if (response.ok) {
    return await response.json();
  }

  let errorDetail = `Request failed with status ${response.status}`;
  try {
    const errorData = await response.json();
    if (errorData) {
      if (typeof errorData.detail === "string") {
        errorDetail = errorData.detail;
      } else if (Array.isArray(errorData.detail)) {
        errorDetail = errorData.detail
          .map((d) => (d.msg ? `${d.loc ? d.loc.join(".") + ": " : ""}${d.msg}` : JSON.stringify(d)))
          .join(", ");
      } else if (errorData.message) {
        errorDetail = errorData.message;
      } else if (errorData.error) {
        errorDetail = errorData.error;
      }
    }
  } catch {
    try {
      const text = await response.text();
      if (text) errorDetail = text;
    } catch {
      // ignore
    }
  }

  const error = new Error(errorDetail);
  error.status = response.status;
  throw error;
}

/**
 * Start a research session for a given topic.
 * POST /research { topic } -> { session_id }
 */
export async function startResearch(topic) {
  const response = await fetch(`${API_BASE}/research`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ topic }),
  });
  return handleResponse(response);
}

/**
 * Retrieve synthesized research findings and claims.
 * GET /research/{session_id} -> FindingsPacket
 */
export async function getResearchResults(sessionId) {
  const response = await fetch(`${API_BASE}/research/${sessionId}`, {
    method: "GET",
    headers: { Accept: "application/json" },
  });
  return handleResponse(response);
}

/**
 * Run grounded question answering on ingested research papers.
 * POST /research/{session_id}/qa { question } -> { answer, source_paper_ids }
 */
export async function askQuestion(sessionId, question) {
  const response = await fetch(`${API_BASE}/research/${sessionId}/qa`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ question }),
  });
  return handleResponse(response);
}

/**
 * Select desired output deliverables and determine next guided input tier.
 * POST /research/{session_id}/outputs { output_types } -> { next_tier }
 */
export async function selectOutputs(sessionId, outputTypes) {
  const response = await fetch(`${API_BASE}/research/${sessionId}/outputs`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ output_types: outputTypes }),
  });
  return handleResponse(response);
}

/**
 * Submit answers for a specific guided input tier.
 * POST /research/{session_id}/guided-input { tier, value } -> { ok, error, next_tier, is_complete }
 */
export async function submitGuidedInputTier(sessionId, tier, value) {
  const response = await fetch(`${API_BASE}/research/${sessionId}/guided-input`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ tier, value }),
  });
  return handleResponse(response);
}

/**
 * Start the background document composition graph.
 * POST /research/{session_id}/compose -> { session_id, status: "composing" }
 */
export async function composeDocuments(sessionId) {
  const response = await fetch(`${API_BASE}/research/${sessionId}/compose`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
  });
  return handleResponse(response);
}

/**
 * Get download links for composed deliverables.
 * GET /research/{session_id}/results -> [{ output_type, download_url }]
 * Throws with status 409 while composition is still running.
 */
export async function getResults(sessionId) {
  const response = await fetch(`${API_BASE}/research/${sessionId}/results`, {
    method: "GET",
    headers: { Accept: "application/json" },
  });
  return handleResponse(response);
}
