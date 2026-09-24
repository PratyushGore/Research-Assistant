import { useLocation, useNavigate } from "react-router-dom";
import "./Outputs.css";

function Outputs() {
  const navigate = useNavigate();
  const location = useLocation();

  const researchData = location.state || {};

  const topic =
    researchData.topic || "Your Research Project";

  const selectedOutputs = Array.isArray(
    researchData.selectedOutputs
  )
    ? researchData.selectedOutputs
    : [];

  const outputs = [
    {
      id: "literature_survey",
      number: "01",
      title: "Literature Survey",
      description:
        "A structured synthesis of existing research, major themes, findings, and research gaps.",
      icon: "⌘",
      format: "DOCX / PDF",
    },
    {
      id: "executive_summary",
      number: "02",
      title: "Executive Summary",
      description:
        "A concise overview of the research with key findings and important implications.",
      icon: "✦",
      format: "DOCX / PDF",
    },
    {
      id: "ppt",
      number: "03",
      title: "Research Presentation",
      description:
        "A structured presentation covering the problem, literature findings, approach, results, and conclusion.",
      icon: "▣",
      format: "PPTX",
    },
    {
      id: "research_paper",
      number: "04",
      title: "Research Paper",
      description:
        "A structured academic paper containing the literature review, methodology, results, discussion, and references.",
      icon: "◇",
      format: "DOCX / PDF",
    },
  ];

  const generatedOutputs = outputs.filter((output) =>
    selectedOutputs.includes(output.id)
  );

  const handleBack = () => {
    navigate("/research");
  };

  const handlePreview = (output) => {
    alert(
      `${output.title} preview will be connected to the generated document after backend integration.`
    );
  };

  const handleDownload = (output) => {
    alert(
      `${output.title} download will be connected to the generated file after backend integration.`
    );
  };

  return (
    <div className="outputs-page">

      <div className="outputs-background-glow"></div>

      <header className="outputs-header">

        <div className="outputs-logo">
          <span>✦</span>
          ResearchAI
        </div>

        <button
          type="button"
          className="outputs-home-button"
          onClick={handleBack}
        >
          ← New Research
        </button>

      </header>

      <main className="outputs-container">

        <section className="outputs-intro">

          <div className="outputs-eyebrow">
            <span></span>
            RESEARCH WORKFLOW COMPLETE
          </div>

          <h1>
            Your research is
            <br />
            <span>ready.</span>
          </h1>

          <p>
            Your multi-agent research workflow has completed.
            Review the generated deliverables below.
          </p>

        </section>

        <section className="final-topic-card">

          <div className="final-topic-label">
            RESEARCH TOPIC
          </div>

          <h2>{topic}</h2>

          <div className="final-status">
            <span></span>
            All research agents completed successfully
          </div>

        </section>

        <section className="outputs-section">

          <div className="outputs-section-heading">

            <div>

              <span>
                GENERATED DELIVERABLES
              </span>

              <h2>
                Your research outputs
              </h2>

            </div>

            <div className="output-count">
              {generatedOutputs.length}{" "}
              {generatedOutputs.length === 1
                ? "output"
                : "outputs"}
            </div>

          </div>

          <div className="outputs-grid">

            {generatedOutputs.map((output) => (
              <article
                key={output.id}
                className="generated-output-card"
              >

                <div className="output-card-top">

                  <div className="generated-output-icon">
                    {output.icon}
                  </div>

                  <span className="output-number">
                    {output.number}
                  </span>

                </div>

                <div className="generated-output-content">

                  <h3>
                    {output.title}
                  </h3>

                  <p>
                    {output.description}
                  </p>

                </div>

                <div className="output-card-footer">

                  <span className="file-format">
                    {output.format}
                  </span>

                  <div className="output-actions">

                    <button
                      type="button"
                      className="preview-button"
                      onClick={() =>
                        handlePreview(output)
                      }
                    >
                      Preview
                    </button>

                    <button
                      type="button"
                      className="download-button"
                      onClick={() =>
                        handleDownload(output)
                      }
                    >
                      Download
                      <span>↓</span>
                    </button>

                  </div>

                </div>

              </article>
            ))}

          </div>

        </section>

        <section className="output-summary">

          <div className="summary-icon">
            ✓
          </div>

          <div>

            <h3>
              Research pipeline completed
            </h3>

            <p>
              Search, ingestion, reasoning, verification,
              citation, and output generation have finished.
            </p>

          </div>

        </section>

        <div className="outputs-bottom">

          <button
            type="button"
            className="new-research-button"
            onClick={handleBack}
          >
            Start Another Research Project
            <span>→</span>
          </button>

        </div>

      </main>

    </div>
  );
}

export default Outputs;