import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { startResearch, getLastMaxPapers, setLastMaxPapers } from "../api";
import "./ResearchSetup.css";

function ResearchSetup() {
  const navigate = useNavigate();

  const [topic, setTopic] = useState("");
  const [maxPapers, setMaxPapers] = useState(() => getLastMaxPapers());
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState(null);

  const handleDecrement = () => {
    const current = parseInt(maxPapers, 10) || 8;
    const next = Math.max(3, current - 1);
    setMaxPapers(next);
    setLastMaxPapers(next);
  };

  const handleIncrement = () => {
    const current = parseInt(maxPapers, 10) || 8;
    const next = Math.min(15, current + 1);
    setMaxPapers(next);
    setLastMaxPapers(next);
  };

  const handlePaperCountChange = (event) => {
    const val = event.target.value;
    if (val === "") {
      setMaxPapers("");
      return;
    }
    const num = parseInt(val, 10);
    if (isNaN(num)) return;
    if (num > 15) {
      setMaxPapers(15);
      setLastMaxPapers(15);
    } else {
      setMaxPapers(num);
      if (num >= 3) {
        setLastMaxPapers(num);
      }
    }
  };

  const handlePaperCountBlur = () => {
    const num = parseInt(maxPapers, 10);
    if (isNaN(num) || num < 3) {
      setMaxPapers(3);
      setLastMaxPapers(3);
    } else if (num > 15) {
      setMaxPapers(15);
      setLastMaxPapers(15);
    } else {
      setMaxPapers(num);
      setLastMaxPapers(num);
    }
  };

  const handleContinue = async () => {
    const cleanedTopic = topic.trim();

    if (!cleanedTopic || isLoading) {
      return;
    }

    const validatedPapers = setLastMaxPapers(maxPapers);
    setMaxPapers(validatedPapers);
    setIsLoading(true);
    setError(null);

    try {
      const response = await startResearch(cleanedTopic, validatedPapers);
      navigate("/research-progress", {
        state: {
          session_id: response.session_id,
          topic: cleanedTopic,
          max_papers: validatedPapers,
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

          {/* Number of research papers */}
          <div className="paper-count-section">
            <label htmlFor="max-papers-input">
              Number of research papers
            </label>

            <div className="stepper-control">
              <button
                type="button"
                className="stepper-button"
                onClick={handleDecrement}
                disabled={isLoading || (typeof maxPapers === "number" ? maxPapers <= 3 : parseInt(maxPapers, 10) <= 3)}
                aria-label="Decrease papers"
              >
                -
              </button>

              <input
                id="max-papers-input"
                className="stepper-input"
                type="number"
                min="3"
                max="15"
                value={maxPapers}
                onChange={handlePaperCountChange}
                onBlur={handlePaperCountBlur}
                aria-label="Number of research papers"
              />

              <button
                type="button"
                className="stepper-button"
                onClick={handleIncrement}
                disabled={isLoading || (typeof maxPapers === "number" ? maxPapers >= 15 : parseInt(maxPapers, 10) >= 15)}
                aria-label="Increase papers"
              >
                +
              </button>
            </div>

            <div className="input-hint">
              More papers take longer to analyse
            </div>
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