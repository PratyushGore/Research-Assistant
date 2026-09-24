import { useNavigate } from "react-router-dom";
import "../App.css";

function Home() {
  const navigate = useNavigate();

  return (
    <div className="app">
      {/* Navigation */}
      <nav className="navbar">
        <div className="logo">
          <span className="logo-mark">✦</span>
          <span>ResearchAI</span>
        </div>

        <div className="nav-links">
          <a href="#home">Home</a>
          <a href="#how-it-works">How It Works</a>
          <a href="#features">Features</a>
          <a href="#about">About</a>
        </div>

        <button
          className="nav-button"
          onClick={() => navigate("/research")}
        >
          Start Research
        </button>
      </nav>

      {/* Hero Section */}
      <main id="home" className="hero">
        <div className="hero-glow"></div>

        <div className="hero-content">
          <div className="eyebrow">
            <span className="status-dot"></span>
            Multi-Agent Research Intelligence
          </div>

          <h1>
            Research smarter.
            <br />
            <span>Publish better.</span>
          </h1>

          <p>
            An intelligent multi-agent research assistant that searches,
            analyzes, verifies, and transforms research into meaningful
            academic outputs.
          </p>

          <div className="hero-actions">
            <button
              className="primary-button"
              onClick={() => navigate("/research")}
            >
              Start a Research Project
            </button>

            <button
              className="secondary-button"
              onClick={() =>
                document
                  .getElementById("workflow")
                  ?.scrollIntoView({ behavior: "smooth" })
              }
            >
              Explore the workflow →
            </button>
          </div>
        </div>

        {/* AI Agent Network */}
        <div className="ai-network">
          <div className="network-line line-one"></div>
          <div className="network-line line-two"></div>
          <div className="network-line line-three"></div>
          <div className="network-line line-four"></div>

          <div className="agent-card agent-search">
            <span>⌕</span>

            <div>
              <strong>Search Agent</strong>
              <small>Find relevant papers</small>
            </div>
          </div>

          <div className="agent-card agent-summary">
            <span>✦</span>

            <div>
              <strong>Reasoning Agent</strong>
              <small>Analyze research</small>
            </div>
          </div>

          <div className="agent-card agent-verify">
            <span>✓</span>

            <div>
              <strong>Verification</strong>
              <small>Check every claim</small>
            </div>
          </div>

          <div className="agent-card agent-output">
            <span>↗</span>

            <div>
              <strong>Output Agent</strong>
              <small>Create documents</small>
            </div>
          </div>

          <div className="ai-core">
            <div className="core-inner">
              <span>AI</span>
            </div>
          </div>
        </div>
      </main>

      {/* Workflow Preview */}
      <section
        id="workflow"
        className="preview-section"
      >
        <p>
          One intelligent workflow from research discovery to final output
        </p>

        <div className="workflow-preview">
          <div>Paper Discovery</div>
          <span>→</span>

          <div>Research Understanding</div>
          <span>→</span>

          <div>Claim Verification</div>
          <span>→</span>

          <div>Publication</div>
        </div>
      </section>
    </div>
  );
}

export default Home;