import { useEffect, useState, useRef, useMemo } from "react";
import { useLocation, useNavigate } from "react-router-dom";
import {
  getResearchWsUrl,
  getResults,
  composeDocuments,
  startResearch,
} from "../api";
import "./ResearchProgress.css";

const STAGE_ORDER = [
  "search",
  "ingestion",
  "summarization",
  "verification",
  "citation",
];

function ResearchProgress() {
  const navigate = useNavigate();
  const location = useLocation();

  const researchData = location.state || {};
  const topic = researchData.topic || "Your Research Project";
  const sessionId = researchData.session_id;
  const phase = researchData.phase || (researchData.guidedInput ? "compose" : "research");

  const selectedOutputs = useMemo(() => {
    return Array.isArray(researchData.selectedOutputs)
      ? researchData.selectedOutputs
      : [];
  }, [researchData.selectedOutputs]);

  const agents = [
    {
      id: "search",
      number: "01",
      name: "Search Agent",
      description: "Finding relevant research papers",
      icon: "⌕",
    },
    {
      id: "ingestion",
      number: "02",
      name: "Ingestion Agent",
      description: "Understanding papers and extracting content",
      icon: "◈",
    },
    {
      id: "reasoning",
      number: "03",
      name: "Reasoning Agent",
      description: "Analyzing research and identifying findings",
      icon: "✦",
    },
    {
      id: "verification",
      number: "04",
      name: "Verification Agent",
      description: "Checking claims against source evidence",
      icon: "✓",
    },
    {
      id: "citation",
      number: "05",
      name: "Citation Agent",
      description: "Preparing accurate academic citations",
      icon: "⌘",
    },
    {
      id: "composer",
      number: "06",
      name: "Output Agent",
      description: "Generating your research deliverables",
      icon: "↗",
    },
  ];

  const [currentAgent, setCurrentAgent] = useState(
    phase === "compose" ? 5 : 0
  );
  const [completedAgents, setCompletedAgents] = useState(
    phase === "compose" ? [0, 1, 2, 3, 4] : []
  );
  const [statusDetail, setStatusDetail] = useState(
    phase === "compose"
      ? "Generating deliverables..."
      : "Initializing research agents..."
  );
  const [errorMessage, setErrorMessage] = useState(null);
  const [isRetrying, setIsRetrying] = useState(false);

  // Guard against navigating multiple times
  const hasNavigatedRef = useRef(false);

  // ---------------------------------------------------------------------------
  // Phase 1: Research via WebSocket
  // ---------------------------------------------------------------------------
  useEffect(() => {
    if (phase !== "research") return;

    if (!sessionId) {
      setErrorMessage("No active research session ID found. Please start from Research Setup.");
      return;
    }

    hasNavigatedRef.current = false;
    setErrorMessage(null);
    let isMounted = true;

    const wsUrl = getResearchWsUrl(sessionId);
    const ws = new WebSocket(wsUrl);

    ws.onopen = () => {
      if (isMounted) {
        setStatusDetail("Connected to research pipeline.");
      }
    };

    ws.onmessage = (event) => {
      if (!isMounted) return;

      try {
        const data = JSON.parse(event.data);
        const stage = data.stage;
        const detail = data.detail;

        if (detail) {
          setStatusDetail(detail);
        }

        if (stage === "failed") {
          setErrorMessage(detail || "Research pipeline failed. Please retry.");
          return;
        }

        if (stage === "research_done") {
          setCompletedAgents([0, 1, 2, 3, 4]);
          setCurrentAgent(4);
          if (!hasNavigatedRef.current) {
            hasNavigatedRef.current = true;
            setTimeout(() => {
              if (isMounted) {
                navigate("/research-results", {
                  state: {
                    session_id: sessionId,
                    topic,
                  },
                });
              }
            }, 600);
          }
          return;
        }

        const stageIdx = STAGE_ORDER.indexOf(stage);
        if (stageIdx !== -1) {
          setCompletedAgents((prev) => {
            const nextCompleted = new Set(prev);
            for (let i = 0; i <= stageIdx; i++) {
              nextCompleted.add(i);
            }
            return Array.from(nextCompleted);
          });

          if (stageIdx < 4) {
            setCurrentAgent(stageIdx + 1);
          }
        }
      } catch (err) {
        console.error("Failed to parse WebSocket event:", err);
      }
    };

    ws.onerror = (err) => {
      if (!isMounted) return;
      console.error("WebSocket connection error:", err);
      setErrorMessage("WebSocket connection error. Unable to stream live research progress.");
    };

    ws.onclose = () => {
      // ws closed after completion or server termination
    };

    return () => {
      isMounted = false;
      ws.close();
    };
  }, [phase, sessionId, topic, navigate]);

  // ---------------------------------------------------------------------------
  // Phase 2: Compose via Polling GET /research/{session_id}/results
  // ---------------------------------------------------------------------------
  useEffect(() => {
    if (phase !== "compose") return;

    if (!sessionId) {
      setErrorMessage("No active session ID for document composition. Please start from Research Setup.");
      return;
    }

    hasNavigatedRef.current = false;
    setErrorMessage(null);
    let isMounted = true;
    const startTime = Date.now();
    const TIMEOUT_MS = 120000; // 2 minutes

    const pollInterval = setInterval(async () => {
      if (!isMounted) return;

      if (Date.now() - startTime > TIMEOUT_MS) {
        clearInterval(pollInterval);
        setErrorMessage("Document composition timed out after 2 minutes. Please retry.");
        return;
      }

      try {
        const results = await getResults(sessionId);
        if (!isMounted) return;

        clearInterval(pollInterval);
        setCompletedAgents([0, 1, 2, 3, 4, 5]);
        setCurrentAgent(5);
        setStatusDetail("Deliverables composed successfully.");

        if (!hasNavigatedRef.current) {
          hasNavigatedRef.current = true;
          setTimeout(() => {
            if (isMounted) {
              navigate("/outputs", {
                state: {
                  session_id: sessionId,
                  topic,
                  selectedOutputs,
                  results,
                },
              });
            }
          }, 600);
        }
      } catch (err) {
        if (!isMounted) return;

        // 409 Conflict: composition is still in progress, keep polling
        if (err.status === 409) {
          setStatusDetail("Composing output documents...");
          return;
        }

        // Real failure (404, 500, network error)
        clearInterval(pollInterval);
        setErrorMessage(err.message || "Failed to retrieve generated deliverables.");
      }
    }, 2000);

    return () => {
      isMounted = false;
      clearInterval(pollInterval);
    };
  }, [phase, sessionId, topic, selectedOutputs, navigate]);

  // Retry handler for both phases
  const handleRetry = async () => {
    setIsRetrying(true);
    setErrorMessage(null);

    try {
      if (phase === "compose") {
        await composeDocuments(sessionId);
        setIsRetrying(false);
        // Force component state update to restart polling
        window.location.reload();
      } else {
        const response = await startResearch(topic);
        setIsRetrying(false);
        navigate("/research-progress", {
          state: {
            session_id: response.session_id,
            topic,
            phase: "research",
          },
          replace: true,
        });
      }
    } catch (err) {
      setIsRetrying(false);
      setErrorMessage(err.message || "Retry attempt failed. Please check the backend service.");
    }
  };

  const isComplete =
    phase === "compose"
      ? completedAgents.length === agents.length
      : completedAgents.length >= 5;

  const totalSteps = phase === "compose" ? agents.length : 5;
  const progressPercentage = isComplete
    ? 100
    : Math.min(
        100,
        Math.round((completedAgents.length / totalSteps) * 100)
      );

  const getOutputName = (output) => {
    const names = {
      literature_survey: "Literature Survey",
      executive_summary: "Executive Summary",
      ppt: "Presentation",
      research_paper: "Research Paper",
    };

    return names[output] || output;
  };

  return (
    <div className="progress-page">
      <div className="progress-background-glow"></div>

      <header className="progress-header">
        <div className="progress-logo">
          <span>✦</span>
          ResearchAI
        </div>

        <div className="live-indicator">
          <span></span>
          {errorMessage
            ? "ATTENTION REQUIRED"
            : isComplete
            ? "RESEARCH COMPLETE"
            : phase === "compose"
            ? "COMPOSING DELIVERABLES"
            : "LIVE RESEARCH"}
        </div>
      </header>

      <main className="progress-container">
        <section className="progress-intro">
          <div className="progress-eyebrow">
            <span></span>
            {phase === "compose"
              ? "DOCUMENT COMPOSITION PIPELINE"
              : "MULTI-AGENT RESEARCH WORKFLOW"}
          </div>

          <h1>
            {errorMessage ? (
              <>
                Pipeline
                <br />
                <span style={{ color: "#f87171" }}>interrupted.</span>
              </>
            ) : isComplete ? (
              <>
                Your research is
                <br />
                <span>ready.</span>
              </>
            ) : (
              <>
                Your research is
                <br />
                <span>being analyzed.</span>
              </>
            )}
          </h1>

          <p>
            {errorMessage
              ? errorMessage
              : isComplete
              ? phase === "compose"
                ? "The composition workflow has completed successfully. Your deliverables are ready to review."
                : "The research workflow has completed successfully. Your findings are ready to review."
              : statusDetail || "Our agents are working together to search, understand, verify, and synthesize literature."}
          </p>

          {/* Error Banner with Retry/Back */}
          {errorMessage && (
            <div
              style={{
                marginTop: "16px",
                padding: "16px",
                backgroundColor: "rgba(239, 68, 68, 0.12)",
                border: "1px solid rgba(239, 68, 68, 0.3)",
                borderRadius: "10px",
                color: "#fca5a5",
                display: "flex",
                flexDirection: "column",
                gap: "12px",
              }}
            >
              <div>
                <strong>Error Details:</strong> {errorMessage}
              </div>
              <div style={{ display: "flex", gap: "10px", flexWrap: "wrap" }}>
                <button
                  type="button"
                  onClick={handleRetry}
                  disabled={isRetrying}
                  style={{
                    padding: "8px 16px",
                    backgroundColor: "#ef4444",
                    color: "#ffffff",
                    border: "none",
                    borderRadius: "6px",
                    cursor: "pointer",
                    fontWeight: 600,
                  }}
                >
                  {isRetrying ? "Retrying..." : "↻ Retry Pipeline"}
                </button>
                <button
                  type="button"
                  onClick={() => navigate("/research")}
                  style={{
                    padding: "8px 16px",
                    backgroundColor: "transparent",
                    color: "#e2e8f0",
                    border: "1px solid rgba(255, 255, 255, 0.2)",
                    borderRadius: "6px",
                    cursor: "pointer",
                  }}
                >
                  ← Back to Setup
                </button>
              </div>
            </div>
          )}
        </section>

        <section className="research-topic-card">
          <div className="topic-label">RESEARCH TOPIC</div>
          <h2>{topic}</h2>

          <div className="selected-output-list">
            {selectedOutputs.length > 0 ? (
              selectedOutputs.map((output) => (
                <span key={output}>{getOutputName(output)}</span>
              ))
            ) : (
              <span>Literature Discovery &amp; Verification</span>
            )}
          </div>
        </section>

        <section className="overall-progress-card">
          <div className="overall-progress-header">
            <div>
              <span>OVERALL PROGRESS</span>
              <strong>
                {errorMessage
                  ? "Pipeline Paused"
                  : isComplete
                  ? "Research workflow complete"
                  : agents[currentAgent]?.name}
              </strong>
            </div>

            <div className="progress-percentage">{progressPercentage}%</div>
          </div>

          <div className="progress-track">
            <div
              className="progress-fill"
              style={{
                width: `${progressPercentage}%`,
              }}
            ></div>
          </div>
        </section>

        <section className="agent-workflow">
          <div className="workflow-heading">
            <div>
              <span className="section-eyebrow">AGENT ACTIVITY</span>
              <h2>Research pipeline</h2>
            </div>

            <span className="agent-count">
              {completedAgents.length} / {agents.length} completed
            </span>
          </div>

          <div className="agent-list">
            {agents.map((agent, index) => {
              const isCompleted = completedAgents.includes(index);
              const isActive =
                currentAgent === index && !isCompleted && !errorMessage;
              const isPending = !isCompleted && !isActive;

              return (
                <div
                  key={agent.id}
                  className={`progress-agent-card ${
                    isCompleted ? "completed" : ""
                  } ${isActive ? "active" : ""} ${isPending ? "pending" : ""}`}
                >
                  <div className="agent-number">
                    {isCompleted ? "✓" : agent.number}
                  </div>

                  <div className="agent-icon">{agent.icon}</div>

                  <div className="agent-information">
                    <h3>{agent.name}</h3>
                    <p>{agent.description}</p>
                  </div>

                  <div className="agent-status-text">
                    {isCompleted && "COMPLETED"}

                    {isActive && (
                      <>
                        <span className="loading-dot"></span>
                        WORKING
                      </>
                    )}

                    {isPending && "WAITING"}
                  </div>
                </div>
              );
            })}
          </div>
        </section>

        <div className="progress-footer">
          <div className="secure-status">
            <span></span>
            {errorMessage
              ? "Action required to proceed"
              : isComplete
              ? "Research session completed"
              : "Research session active"}
          </div>

          {isComplete && (
            <button
              type="button"
              className="view-results-button"
              onClick={() => {
                if (phase === "compose") {
                  navigate("/outputs", {
                    state: researchData,
                  });
                } else {
                  navigate("/research-results", {
                    state: {
                      session_id: sessionId,
                      topic,
                      ...researchData,
                    },
                  });
                }
              }}
            >
              {phase === "compose"
                ? "View Generated Outputs"
                : "View Research Results"}
              <span>→</span>
            </button>
          )}
        </div>
      </main>
    </div>
  );
}

export default ResearchProgress;