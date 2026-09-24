import { useEffect, useState } from "react";
import { useLocation, useNavigate } from "react-router-dom";
import "./ResearchProgress.css";

function ResearchProgress() {
  const navigate = useNavigate();
  const location = useLocation();

  const researchData = location.state || {};

  const topic = researchData.topic || "Your Research Project";

  const selectedOutputs = Array.isArray(
    researchData.selectedOutputs
  )
    ? researchData.selectedOutputs
    : [];

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

  const [currentAgent, setCurrentAgent] = useState(0);
  const [completedAgents, setCompletedAgents] = useState([]);

  useEffect(() => {
    const timers = agents.map((_, index) => {
      return setTimeout(() => {
        setCompletedAgents((current) => {
          if (current.includes(index)) {
            return current;
          }

          return [...current, index];
        });

        if (index < agents.length - 1) {
          setCurrentAgent(index + 1);
        }
      }, (index + 1) * 1800);
    });

    return () => {
      timers.forEach((timer) => clearTimeout(timer));
    };
  }, []);

  const isComplete =
    completedAgents.length === agents.length;

  const progressPercentage = isComplete
    ? 100
    : Math.round(
        (completedAgents.length / agents.length) * 100
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

          {isComplete
            ? "RESEARCH COMPLETE"
            : "LIVE RESEARCH"}

        </div>

      </header>

      <main className="progress-container">

        <section className="progress-intro">

          <div className="progress-eyebrow">
            <span></span>
            MULTI-AGENT RESEARCH WORKFLOW
          </div>

          <h1>
            {isComplete ? (
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
            {isComplete
              ? "The research workflow has completed successfully. Your selected outputs are ready to review."
              : "Our agents are working together to search, understand, verify, and transform research into your selected outputs."}
          </p>

        </section>

        <section className="research-topic-card">

          <div className="topic-label">
            RESEARCH TOPIC
          </div>

          <h2>{topic}</h2>

          <div className="selected-output-list">

            {selectedOutputs.map((output) => (
              <span key={output}>
                {getOutputName(output)}
              </span>
            ))}

          </div>

        </section>

        <section className="overall-progress-card">

          <div className="overall-progress-header">

            <div>

              <span>
                OVERALL PROGRESS
              </span>

              <strong>
                {isComplete
                  ? "Research workflow complete"
                  : agents[currentAgent]?.name}
              </strong>

            </div>

            <div className="progress-percentage">
              {progressPercentage}%
            </div>

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

              <span className="section-eyebrow">
                AGENT ACTIVITY
              </span>

              <h2>
                Research pipeline
              </h2>

            </div>

            <span className="agent-count">
              {completedAgents.length} /{" "}
              {agents.length} completed
            </span>

          </div>

          <div className="agent-list">

            {agents.map((agent, index) => {

              const isCompleted =
                completedAgents.includes(index);

              const isActive =
                currentAgent === index &&
                !isCompleted;

              const isPending =
                index > currentAgent;

              return (
                <div
                  key={agent.id}
                  className={`progress-agent-card ${
                    isCompleted
                      ? "completed"
                      : ""
                  } ${
                    isActive
                      ? "active"
                      : ""
                  } ${
                    isPending
                      ? "pending"
                      : ""
                  }`}
                >

                  <div className="agent-number">

                    {isCompleted
                      ? "✓"
                      : agent.number}

                  </div>

                  <div className="agent-icon">
                    {agent.icon}
                  </div>

                  <div className="agent-information">

                    <h3>
                      {agent.name}
                    </h3>

                    <p>
                      {agent.description}
                    </p>

                  </div>

                  <div className="agent-status-text">

                    {isCompleted &&
                      "COMPLETED"}

                    {isActive && (
                      <>
                        <span className="loading-dot"></span>
                        WORKING
                      </>
                    )}

                    {isPending &&
                      "WAITING"}

                  </div>

                </div>
              );
            })}

          </div>

        </section>

        <div className="progress-footer">

          <div className="secure-status">

            <span></span>

            {isComplete
              ? "Research session completed"
              : "Research session active"}

          </div>

          {isComplete && (
            <button
              type="button"
              className="view-results-button"
              onClick={() =>
                navigate("/outputs", {
                  state: researchData,
                })
              }
            >
              View Generated Outputs

              <span>→</span>
            </button>
          )}

        </div>

      </main>

    </div>
  );
}

export default ResearchProgress;