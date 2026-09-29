import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { startResearch } from "../api";
import "./ResearchSetup.css";

function ResearchSetup() {
  const navigate = useNavigate();

  const [topic, setTopic] = useState("");
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState(null);

  const handleContinue = async () => {
    const cleanedTopic = topic.trim();

    if (!cleanedTopic || isLoading) {
      return;
    }

    setIsLoading(true);
    setError(null);

    try {
      const response = await startResearch(cleanedTopic);
      navigate("/research-progress", {
        state: {
          session_id: response.session_id,
          topic: cleanedTopic,
          phase: "research",
        },
      });
    } catch (err) {
      setError(err.message || "Failed to initiate research session. Please verify the backend is running.");
      setIsLoading(false);
    }
  };

  return (
    <div className="setup-page">
      <div className="setup-background-glow"></div>

      {/* Header */}
      <header className="setup-header">
        <div className="setup-logo">
          <span>✦</span>
          ResearchAI
        </div>

        <button
          type="button"
          className="back-button"
          onClick={() => navigate("/")}
        >
          ← Back to Home
        </button>
      </header>

      {/* Main */}
      <main className="setup-container">

        {/* Heading */}
        <div className="setup-heading">
          <div className="setup-eyebrow">
            <span></span>
            NEW RESEARCH PROJECT
          </div>

          <h1>
            What are you
            <br />
            <span>researching?</span>
          </h1>

          <p>
            Tell us what you want to explore. Our agents will autonomously
            search, ingest, synthesize, and verify the literature before you choose your deliverables.
          </p>
        </div>

        {/* Setup Card */}
        <div className="setup-card">

          {/* Topic */}
          <div className="topic-section">
            <label htmlFor="research-topic">
              Research Topic
            </label>

            <textarea
              id="research-topic"
              value={topic}
              onChange={(event) =>
                setTopic(event.target.value)
              }
              placeholder="e.g. Impact of generative AI on software engineering..."
              rows="4"
            />

            <div className="input-hint">
              Be as specific as possible for more relevant research.
            </div>

            {error && (
              <div
                style={{
                  marginTop: "12px",
                  padding: "10px 14px",
                  backgroundColor: "rgba(239, 68, 68, 0.12)",
                  border: "1px solid rgba(239, 68, 68, 0.3)",
                  borderRadius: "8px",
                  color: "#f87171",
                  fontSize: "14px",
                  lineHeight: "1.4",
                }}
              >
                ⚠️ {error}
              </div>
            )}
          </div>

          {/* Footer */}
          <div className="setup-footer">

            <div>
              <span className="agent-status"></span>

              {isLoading ? "Starting research session..." : "Multi-agent workflow ready"}
            </div>

            <button
              type="button"
              className="continue-button"
              disabled={!topic.trim() || isLoading}
              onClick={handleContinue}
            >
              {isLoading ? "Starting..." : "Continue"}

              <span>→</span>
            </button>

          </div>

        </div>
      </main>
    </div>
  );
}

export default ResearchSetup;