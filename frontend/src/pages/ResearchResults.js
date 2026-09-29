import { useEffect, useState, useCallback } from "react";
import { useLocation, useNavigate } from "react-router-dom";
import { getResearchResults, askQuestion, selectOutputs } from "../api";
import "./ResearchResults.css";

function ResearchResults() {
  const navigate = useNavigate();
  const location = useLocation();

  const researchData = location.state || {};
  const sessionId = researchData.session_id;

  const [findings, setFindings] = useState(null);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState(null);

  const [selectedOutputs, setSelectedOutputs] = useState([]);
  const [isSubmittingOutputs, setIsSubmittingOutputs] = useState(false);
  const [outputError, setOutputError] = useState(null);

  const [qaInput, setQaInput] = useState("");
  const [qaHistory, setQaHistory] = useState([]);
  const [isAsking, setIsAsking] = useState(false);
  const [qaError, setQaError] = useState(null);

  const outputs = [
    {
      id: "literature_survey",
      title: "Literature Survey",
      description: "Organize and synthesize existing research",
      icon: "⌘",
    },
    {
      id: "executive_summary",
      title: "Executive Summary",
      description: "Get a concise overview of the research",
      icon: "✦",
    },
    {
      id: "ppt",
      title: "Presentation",
      description: "Generate a structured research presentation",
      icon: "▣",
    },
    {
      id: "research_paper",
      title: "Research Paper",
      description: "Create a structured academic paper",
      icon: "◇",
    },
  ];

  const fetchFindings = useCallback(async () => {
    if (!sessionId) {
      setError("No active research session ID found. Please start from Research Setup.");
      setIsLoading(false);
      return;
    }

    setIsLoading(true);
    setError(null);

    try {
      const data = await getResearchResults(sessionId);
      setFindings(data);
    } catch (err) {
      setError(err.message || "Failed to load research findings. Please check backend connection.");
    } finally {
      setIsLoading(false);
    }
  }, [sessionId]);

  useEffect(() => {
    fetchFindings();
  }, [fetchFindings]);

  const topic =
    findings?.topic ||
    researchData.topic ||
    "Research Findings";

  const summaries = findings?.summaries || [];
  const claims = findings?.claims || [];
  const contradictions = findings?.contradictions || [];
  const overview =
    findings?.cross_paper_synthesis ||
    findings?.synthesized_overview ||
    "";

  const toggleOutput = (id) => {
    setSelectedOutputs((current) => {
      if (current.includes(id)) {
        return current.filter((item) => item !== id);
      }
      return [...current, id];
    });
  };

  const handleAskQuestion = async (e) => {
    e.preventDefault();
    const cleanQuestion = qaInput.trim();
    if (!cleanQuestion || isAsking) return;

    setIsAsking(true);
    setQaError(null);

    try {
      const res = await askQuestion(sessionId, cleanQuestion);
      setQaHistory((prev) => [
        ...prev,
        {
          question: cleanQuestion,
          answer: res.answer,
          sourcePaperIds: res.source_paper_ids || [],
        },
      ]);
      setQaInput("");
    } catch (err) {
      setQaError(err.message || "Failed to answer question. Please try again.");
    } finally {
      setIsAsking(false);
    }
  };

  const handleContinue = async () => {
    if (selectedOutputs.length === 0 || isSubmittingOutputs) return;

    setIsSubmittingOutputs(true);
    setOutputError(null);

    try {
      const res = await selectOutputs(sessionId, selectedOutputs);
      navigate("/guided-input", {
        state: {
          session_id: sessionId,
          topic,
          selectedOutputs: [...selectedOutputs],
          nextTier: res.next_tier,
        },
      });
    } catch (err) {
      setOutputError(err.message || "Failed to select outputs. Please retry.");
      setIsSubmittingOutputs(false);
    }
  };

  const getStatusBadge = (status) => {
    switch (status) {
      case "verified":
        return <span className="status-badge badge-verified">✓ Verified</span>;
      case "pending":
        return (
          <span className="status-badge badge-pending">
            <span className="badge-spinner">⟳</span> Checking...
          </span>
        );
      case "unverified":
      default:
        return (
          <span className="status-badge badge-unverified">✕ Unverified</span>
        );
    }
  };

  if (isLoading) {
    return (
      <div className="results-page">
        <div className="results-background-glow"></div>
        <header className="results-header">
          <div className="results-logo">
            <span>✦</span>
            ResearchAI
          </div>
        </header>
        <main className="results-container">
          <div className="results-heading">
            <div className="results-eyebrow">
              <span></span>
              RETRIEVING FINDINGS
            </div>
            <h1>
              Loading research
              <br />
              <span>findings...</span>
            </h1>
            <p>Fetching synthesized papers, extracted claims, and verification statuses from the backend.</p>
          </div>
        </main>
      </div>
    );
  }

  if (error) {
    return (
      <div className="results-page">
        <div className="results-background-glow"></div>
        <header className="results-header">
          <div className="results-logo">
            <span>✦</span>
            ResearchAI
          </div>
          <button
            type="button"
            className="back-button"
            onClick={() => navigate("/research")}
          >
            ← New Research
          </button>
        </header>
        <main className="results-container">
          <div className="results-heading">
            <div className="results-eyebrow">
              <span></span>
              ERROR LOADING RESULTS
            </div>
            <h1>
              Unable to load
              <br />
              <span style={{ color: "#f87171" }}>research findings.</span>
            </h1>
            <div
              style={{
                marginTop: "16px",
                padding: "16px",
                backgroundColor: "rgba(239, 68, 68, 0.12)",
                border: "1px solid rgba(239, 68, 68, 0.3)",
                borderRadius: "10px",
                color: "#fca5a5",
                maxWidth: "600px",
              }}
            >
              <p style={{ margin: "0 0 12px 0" }}>⚠️ {error}</p>
              <button
                type="button"
                onClick={fetchFindings}
                style={{
                  padding: "8px 16px",
                  backgroundColor: "#ef4444",
                  color: "#fff",
                  border: "none",
                  borderRadius: "6px",
                  cursor: "pointer",
                  fontWeight: 600,
                }}
              >
                ↻ Retry
              </button>
            </div>
          </div>
        </main>
      </div>
    );
  }

  return (
    <div className="results-page">
      <div className="results-background-glow"></div>

      {/* Header */}
      <header className="results-header">
        <div className="results-logo">
          <span>✦</span>
          ResearchAI
        </div>

        <button
          type="button"
          className="back-button"
          onClick={() => navigate("/research")}
        >
          ← New Research
        </button>
      </header>

      {/* Main Container */}
      <main className="results-container">
        {/* Page Heading */}
        <div className="results-heading">
          <div className="results-eyebrow">
            <span></span>
            SYNTHESIZED RESEARCH FINDINGS
          </div>

          <h1>
            Research
            <br />
            <span>Findings &amp; Insights</span>
          </h1>

          <p>
            Our agents have analyzed, cross-referenced, and verified the
            literature. Review the synthesis below, ask questions, and select
            your desired deliverables to proceed.
          </p>
        </div>

        {/* Topic Banner */}
        <div className="topic-banner-card">
          <div className="topic-banner-label">RESEARCH TOPIC</div>
          <h2>{topic}</h2>
          <div className="topic-stats">
            <span>{summaries.length} Paper{summaries.length !== 1 ? "s" : ""} Synthesized</span>
            <span>•</span>
            <span>{claims.length} Claim{claims.length !== 1 ? "s" : ""} Checked</span>
            <span>•</span>
            <span>{contradictions.length} Contradiction{contradictions.length !== 1 ? "s" : ""} Identified</span>
          </div>
        </div>

        {/* 1. Synthesized Overview */}
        <section className="results-section-card">
          <div className="section-header-row">
            <div>
              <span className="card-eyebrow">HIGH-LEVEL SYNTHESIS</span>
              <h2>Cross-Paper Overview</h2>
            </div>
            <span className="section-pill">Synthesized Analysis</span>
          </div>

          <p className="overview-text">
            {overview ||
              `Across the retrieved literature on "${topic}", empirical consensus and key extracted claims have been synthesized by our multi-agent pipeline.`}
          </p>
        </section>

        {/* 2. Per-Paper Summaries */}
        <section className="results-section-card">
          <div className="section-header-row">
            <div>
              <span className="card-eyebrow">LITERATURE EVIDENCE</span>
              <h2>Per-Paper Summaries</h2>
            </div>
            <span className="section-pill">
              {summaries.length} {summaries.length === 1 ? "Source" : "Sources"} Analyzed
            </span>
          </div>

          {summaries.length === 0 ? (
            <p className="section-subtext" style={{ fontStyle: "italic", color: "#94a3b8" }}>
              No individual paper summaries were returned.
            </p>
          ) : (
            <div className="paper-summaries-list">
              {summaries.map((paper, idx) => (
                <div key={paper.paper_id || idx} className="paper-summary-item">
                  <div className="paper-summary-header">
                    <div className="paper-index">
                      {idx + 1 < 10 ? `0${idx + 1}` : idx + 1}
                    </div>
                    <div>
                      <h3>{paper.title || `Paper ID: ${paper.paper_id}`}</h3>
                      <div className="paper-meta">
                        <span>
                          {paper.authors
                            ? Array.isArray(paper.authors)
                              ? paper.authors.join(", ")
                              : paper.authors
                            : `Source ID: ${paper.paper_id}`}
                        </span>
                        {paper.venue && (
                          <>
                            <span>•</span>
                            <span>{paper.venue}</span>
                          </>
                        )}
                      </div>
                    </div>
                  </div>

                  <p className="paper-abstract">{paper.summary}</p>

                  {paper.key_findings && paper.key_findings.length > 0 && (
                    <div className="paper-key-findings">
                      <strong>Key Findings:</strong>
                      <ul>
                        {paper.key_findings.map((finding, fIdx) => (
                          <li key={fIdx}>{finding}</li>
                        ))}
                      </ul>
                    </div>
                  )}
                </div>
              ))}
            </div>
          )}
        </section>

        {/* 3. Claims with Verification Status */}
        <section className="results-section-card">
          <div className="section-header-row">
            <div>
              <span className="card-eyebrow">EVIDENCE VERIFICATION</span>
              <h2>Extracted Claims &amp; Validation Status</h2>
            </div>
            <span className="section-pill">{claims.length} Claims Checked</span>
          </div>

          <p className="section-subtext">
            Each statement extracted from the literature is cross-referenced
            against source chunks and evaluated for empirical support.
          </p>

          {claims.length === 0 ? (
            <p className="section-subtext" style={{ fontStyle: "italic", color: "#94a3b8" }}>
              No claims were extracted for this research topic.
            </p>
          ) : (
            <div className="claims-list">
              {claims.map((claim, idx) => (
                <div key={claim.claim_id || claim.id || idx} className="claim-item">
                  <div className="claim-body">
                    <span className="claim-id">
                      {claim.claim_id || claim.id || `CLM-00${idx + 1}`}
                    </span>
                    <p className="claim-text">"{claim.text}"</p>
                    <span className="claim-source">
                      Source: {claim.source_paper_id || claim.source || "Ingested Literature"}
                    </span>
                  </div>
                  <div className="claim-status-col">
                    {getStatusBadge(claim.verification_status)}
                  </div>
                </div>
              ))}
            </div>
          )}
        </section>

        {/* 4. Contradictions List */}
        <section className="results-section-card contradictions-card">
          <div className="section-header-row">
            <div>
              <span className="card-eyebrow contradiction-eyebrow">
                DETECTED DISCREPANCIES
              </span>
              <h2>Literature Contradictions</h2>
            </div>
            <span className="section-pill contradiction-pill">
              {contradictions.length} Conflicting Findings
            </span>
          </div>

          <p className="section-subtext">
            Our reasoning agent detected divergent findings between studies.
            These divergences represent active research debates or differing
            experimental methodologies.
          </p>

          {contradictions.length === 0 ? (
            <p className="section-subtext" style={{ fontStyle: "italic", color: "#94a3b8" }}>
              No conflicting findings or contradictions were detected across the analyzed papers.
            </p>
          ) : (
            <div className="contradictions-list">
              {contradictions.map((item, idx) => {
                const isString = typeof item === "string";
                const title = isString
                  ? `Contradiction 0${idx + 1}`
                  : item.title || `Contradiction 0${idx + 1}`;
                const description = isString
                  ? item
                  : item.description || item.text || "";
                const papers = !isString ? item.papers : null;

                return (
                  <div key={idx} className="contradiction-item">
                    <div className="contradiction-header">
                      <div className="contradiction-icon">⚡</div>
                      <h3>{title}</h3>
                    </div>
                    <p className="contradiction-text">{description}</p>
                    {papers && (
                      <div className="contradiction-papers">
                        <strong>Contrasting Sources:</strong> {papers}
                      </div>
                    )}
                  </div>
                );
              })}
            </div>
          )}
        </section>

        {/* 5. Interactive Q&A Box */}
        <section className="results-section-card qa-card">
          <div className="section-header-row">
            <div>
              <span className="card-eyebrow">INTERACTIVE EXPLORATION</span>
              <h2>Ask Questions on These Findings</h2>
            </div>
            <span className="section-pill">Research Q&amp;A</span>
          </div>

          <p className="section-subtext">
            Query the analyzed findings, probe evidence, or clarify specific
            paper claims. Answers are grounded in the ingested literature.
          </p>

          <form onSubmit={handleAskQuestion} className="qa-input-form">
            <input
              type="text"
              value={qaInput}
              onChange={(e) => setQaInput(e.target.value)}
              placeholder="e.g. Which paper analyzed developer cognitive load?"
              className="qa-text-input"
              disabled={isAsking}
            />
            <button
              type="submit"
              disabled={!qaInput.trim() || isAsking}
              className="qa-submit-button"
            >
              {isAsking ? "Asking..." : "Ask Question"}
            </button>
          </form>

          {qaError && (
            <div
              style={{
                marginTop: "10px",
                padding: "10px 14px",
                backgroundColor: "rgba(239, 68, 68, 0.12)",
                border: "1px solid rgba(239, 68, 68, 0.3)",
                borderRadius: "8px",
                color: "#f87171",
                fontSize: "14px",
              }}
            >
              ⚠️ {qaError}
            </div>
          )}

          <div className="qa-history-container">
            {qaHistory.map((item, idx) => (
              <div key={idx} className="qa-history-item">
                <div className="qa-question-row">
                  <span className="qa-q-badge">Q</span>
                  <strong>{item.question}</strong>
                </div>
                <div className="qa-answer-row">
                  <span className="qa-a-badge">A</span>
                  <div>
                    <p style={{ margin: "0 0 6px 0" }}>{item.answer}</p>
                    {item.sourcePaperIds && item.sourcePaperIds.length > 0 && (
                      <span
                        style={{
                          fontSize: "12px",
                          color: "#94a3b8",
                          display: "inline-block",
                        }}
                      >
                        Grounding Sources: {item.sourcePaperIds.join(", ")}
                      </span>
                    )}
                  </div>
                </div>
              </div>
            ))}
          </div>
        </section>

        {/* 6. Deliverable Selection Grid */}
        <section className="results-section-card outputs-card">
          <div className="section-header-row">
            <div>
              <span className="card-eyebrow">DELIVERABLES</span>
              <h2>Select Output Types to Generate</h2>
            </div>
            <span className="output-counter">
              {selectedOutputs.length} selected
            </span>
          </div>

          <p className="section-subtext">
            Choose the deliverables you want our composition agents to produce
            from these synthesized findings.
          </p>

          <div className="output-grid">
            {outputs.map((output) => {
              const isSelected = selectedOutputs.includes(output.id);

              return (
                <button
                  key={output.id}
                  type="button"
                  className={`output-card ${isSelected ? "selected" : ""}`}
                  onClick={() => toggleOutput(output.id)}
                >
                  <div className="output-icon">{output.icon}</div>

                  <div className="output-content">
                    <strong>{output.title}</strong>
                    <p>{output.description}</p>
                  </div>

                  <div className="selection-indicator">
                    {isSelected ? "✓" : ""}
                  </div>
                </button>
              );
            })}
          </div>

          {outputError && (
            <div
              style={{
                marginTop: "14px",
                padding: "10px 14px",
                backgroundColor: "rgba(239, 68, 68, 0.12)",
                border: "1px solid rgba(239, 68, 68, 0.3)",
                borderRadius: "8px",
                color: "#f87171",
                fontSize: "14px",
              }}
            >
              ⚠️ {outputError}
            </div>
          )}

          {/* Action Footer */}
          <div className="results-action-footer">
            <div className="action-status-info">
              <span className="agent-status"></span>
              {selectedOutputs.length === 0
                ? "Select at least one output to continue"
                : `${selectedOutputs.length} output${
                    selectedOutputs.length > 1 ? "s" : ""
                  } selected — ready for guided configuration`}
            </div>

            <button
              type="button"
              className="continue-button"
              disabled={selectedOutputs.length === 0 || isSubmittingOutputs}
              onClick={handleContinue}
            >
              {isSubmittingOutputs ? "Saving Selection..." : "Continue to Guided Input"}
              <span>→</span>
            </button>
          </div>
        </section>
      </main>
    </div>
  );
}

export default ResearchResults;
