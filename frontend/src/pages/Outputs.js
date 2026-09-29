import { useEffect, useState } from "react";
import { useLocation, useNavigate } from "react-router-dom";
import { getDownloadUrl, getResults } from "../api";
import "./Outputs.css";

function Outputs() {
  const navigate = useNavigate();
  const location = useLocation();

  const researchData = location.state || {};
  const sessionId = researchData.session_id;
  const topic = researchData.topic || "Your Research Project";

  const [resultsList, setResultsList] = useState(
    Array.isArray(researchData.results) ? researchData.results : []
  );
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);

  // If results were not in state but session_id is available, fetch them
  useEffect(() => {
    if (resultsList.length === 0 && sessionId) {
      setLoading(true);
      getResults(sessionId)
        .then((res) => {
          setResultsList(res);
        })
        .catch((err) => {
          setError(err.message || "Failed to load generated deliverables.");
        })
        .finally(() => {
          setLoading(false);
        });
    }
  }, [sessionId, resultsList.length]);

  const rawSelectedOutputs = Array.isArray(researchData.selectedOutputs)
    ? researchData.selectedOutputs
    : [];

  // Fallback: derive selected output types from resultsList if not in state
  const selectedOutputs =
    rawSelectedOutputs.length > 0
      ? rawSelectedOutputs
      : resultsList.map((r) =>
          typeof r.output_type === "object"
            ? r.output_type?.value
            : r.output_type
        );

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
    selectedOutputs.some(
      (sel) => (typeof sel === "string" ? sel : sel?.value) === output.id
    )
  );

  const handleBack = () => {
    navigate("/research");
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
            Your multi-agent research workflow has completed. Review the
            generated deliverables below.
          </p>

          {error && (
            <div
              style={{
                marginTop: "16px",
                padding: "14px",
                backgroundColor: "rgba(239, 68, 68, 0.12)",
                border: "1px solid rgba(239, 68, 68, 0.3)",
                borderRadius: "8px",
                color: "#f87171",
                fontSize: "14px",
              }}
            >
              ⚠️ {error}
            </div>
          )}

          {loading && (
            <p style={{ color: "#94a3b8", fontStyle: "italic" }}>
              Retrieving download links...
            </p>
          )}
        </section>

        <section className="final-topic-card">
          <div className="final-topic-label">RESEARCH TOPIC</div>
          <h2>{topic}</h2>

          <div className="final-status">
            <span></span>
            All research agents completed successfully
          </div>
        </section>

        <section className="outputs-section">
          <div className="outputs-section-heading">
            <div>
              <span>GENERATED DELIVERABLES</span>
              <h2>Your research outputs</h2>
            </div>

            <div className="output-count">
              {generatedOutputs.length}{" "}
              {generatedOutputs.length === 1 ? "output" : "outputs"}
            </div>
          </div>

          <div className="outputs-grid">
            {generatedOutputs.map((output) => {
              const resultItem = resultsList.find((r) => {
                const ot =
                  typeof r.output_type === "object"
                    ? r.output_type?.value
                    : r.output_type;
                return String(ot).toLowerCase() === output.id.toLowerCase();
              });

              const downloadUrl = resultItem
                ? getDownloadUrl(resultItem.download_url)
                : null;

              return (
                <article key={output.id} className="generated-output-card">
                  <div className="output-card-top">
                    <div className="generated-output-icon">{output.icon}</div>
                    <span className="output-number">{output.number}</span>
                  </div>

                  <div className="generated-output-content">
                    <h3>{output.title}</h3>
                    <p>{output.description}</p>
                  </div>

                  <div className="output-card-footer">
                    <span className="file-format">{output.format}</span>

                    <div className="output-actions">
                      {downloadUrl ? (
                        <>
                          <a
                            href={downloadUrl}
                            target="_blank"
                            rel="noopener noreferrer"
                            className="preview-button"
                            style={{
                              textDecoration: "none",
                              display: "inline-flex",
                              alignItems: "center",
                              justifyContent: "center",
                            }}
                          >
                            Preview
                          </a>

                          <a
                            href={downloadUrl}
                            download
                            className="download-button"
                            target="_blank"
                            rel="noopener noreferrer"
                            style={{
                              textDecoration: "none",
                              display: "inline-flex",
                              alignItems: "center",
                              justifyContent: "center",
                            }}
                          >
                            Download
                            <span>↓</span>
                          </a>
                        </>
                      ) : (
                        <button
                          type="button"
                          className="download-button"
                          disabled
                          style={{ opacity: 0.5, cursor: "not-allowed" }}
                        >
                          Unavailable
                        </button>
                      )}
                    </div>
                  </div>
                </article>
              );
            })}
          </div>
        </section>

        <section className="output-summary">
          <div className="summary-icon">✓</div>

          <div>
            <h3>Research pipeline completed</h3>
            <p>
              Search, ingestion, reasoning, verification, citation, and output
              generation have finished.
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