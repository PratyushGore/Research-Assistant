import { useState } from "react";
import { useNavigate } from "react-router-dom";
import "./ResearchSetup.css";

function ResearchSetup() {
  const navigate = useNavigate();

  const [topic, setTopic] = useState("");
  const [selectedOutputs, setSelectedOutputs] = useState([]);

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

  const toggleOutput = (id) => {
    setSelectedOutputs((current) => {
      if (current.includes(id)) {
        return current.filter((item) => item !== id);
      }

      return [...current, id];
    });
  };

  const handleContinue = () => {
    const cleanedTopic = topic.trim();

    if (!cleanedTopic) {
      return;
    }

    if (selectedOutputs.length === 0) {
      return;
    }

    navigate("/guided-input", {
      state: {
        topic: cleanedTopic,
        selectedOutputs: [...selectedOutputs],
      },
    });
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
            Tell us what you want to explore and choose the outputs
            you need. Our agents will handle the research workflow.
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
          </div>

          {/* Outputs */}
          <div className="output-section">

            <div className="section-title">
              <div>
                <label>Choose your outputs</label>

                <p>
                  Select one or more deliverables.
                </p>
              </div>

              <span>
                {selectedOutputs.length} selected
              </span>
            </div>

            <div className="output-grid">

              {outputs.map((output) => {
                const isSelected =
                  selectedOutputs.includes(output.id);

                return (
                  <button
                    key={output.id}
                    type="button"
                    className={`output-card ${
                      isSelected ? "selected" : ""
                    }`}
                    onClick={() =>
                      toggleOutput(output.id)
                    }
                  >
                    <div className="output-icon">
                      {output.icon}
                    </div>

                    <div className="output-content">
                      <strong>
                        {output.title}
                      </strong>

                      <p>
                        {output.description}
                      </p>
                    </div>

                    <div className="selection-indicator">
                      {isSelected ? "✓" : ""}
                    </div>
                  </button>
                );
              })}

            </div>
          </div>

          {/* Footer */}
          <div className="setup-footer">

            <div>
              <span className="agent-status"></span>

              Multi-agent workflow ready
            </div>

            <button
              type="button"
              className="continue-button"
              disabled={
                !topic.trim() ||
                selectedOutputs.length === 0
              }
              onClick={handleContinue}
            >
              Continue

              <span>→</span>
            </button>

          </div>

        </div>
      </main>
    </div>
  );
}

export default ResearchSetup;