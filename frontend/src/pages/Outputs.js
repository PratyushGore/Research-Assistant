import { useEffect, useState, useRef, useCallback } from "react";
import { useLocation, useNavigate } from "react-router-dom";
import { getDownloadUrl, getResults, fetchDeliverableFile } from "../api";
import "./Outputs.css";

/**
 * Determine deliverable file type for preview rendering.
 * Supports docx, pptx, and pdf based on download URL or deliverable ID.
 */
export function getDeliverableFileType(resultItem, outputDef) {
  const url = (resultItem?.download_url || "").toLowerCase();
  if (url.includes(".docx")) return "docx";
  if (url.includes(".pptx")) return "pptx";
  if (url.includes(".pdf")) return "pdf";
  const id = (outputDef?.id || "").toLowerCase();
  if (id === "ppt") return "pptx";
  return "docx";
}

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

  // Preview modal state & refs
  const [previewModal, setPreviewModal] = useState({
    isOpen: false,
    title: "",
    downloadUrl: "",
    fileType: "",
    isLoading: false,
    error: null,
    pdfBlobUrl: null,
  });

  const previewContainerRef = useRef(null);
  const pptxPreviewerRef = useRef(null);
  const modalRef = useRef(null);
  const closeButtonRef = useRef(null);
  const currentBlobUrlRef = useRef(null);


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

  const handleClosePreview = useCallback(() => {
    if (currentBlobUrlRef.current) {
      URL.revokeObjectURL(currentBlobUrlRef.current);
      currentBlobUrlRef.current = null;
    }
    if (pptxPreviewerRef.current) {
      try {
        pptxPreviewerRef.current.destroy?.();
      } catch {
        // ignore
      }
      pptxPreviewerRef.current = null;
    }
    if (previewContainerRef.current) {
      previewContainerRef.current.innerHTML = "";
    }
    document.body.style.overflow = "";

    setPreviewModal({
      isOpen: false,
      title: "",
      downloadUrl: "",
      fileType: "",
      isLoading: false,
      error: null,
      pdfBlobUrl: null,
    });
  }, []);

  const handleOpenPreview = async (output, resultItem) => {
    const downloadUrl = resultItem
      ? getDownloadUrl(resultItem.download_url)
      : null;
    if (!downloadUrl) return;

    const fileType = getDeliverableFileType(resultItem, output);

    setPreviewModal({
      isOpen: true,
      title: output.title,
      downloadUrl,
      fileType,
      isLoading: true,
      error: null,
      pdfBlobUrl: null,
    });

    document.body.style.overflow = "hidden";

    try {
      const { blob, arrayBuffer } = await fetchDeliverableFile(downloadUrl);

      if (fileType === "docx") {
        const docxModule = await import("docx-preview");
        const renderAsync =
          docxModule.renderAsync || docxModule.default?.renderAsync;
        if (!renderAsync) {
          throw new Error("docx-preview rendering engine not available.");
        }
        setPreviewModal((prev) => ({ ...prev, isLoading: false }));
        setTimeout(async () => {
          if (previewContainerRef.current) {
            previewContainerRef.current.innerHTML = "";
            await renderAsync(
              arrayBuffer,
              previewContainerRef.current,
              undefined,
              {
                inWrapper: true,
                ignoreWidth: false,
                breakPages: true,
              }
            );
          }
        }, 0);
      } else if (fileType === "pptx") {
        const pptxModule = await import("pptx-preview");
        const init = pptxModule.init || pptxModule.default?.init;
        if (!init) {
          throw new Error("pptx-preview rendering engine not available.");
        }
        setPreviewModal((prev) => ({ ...prev, isLoading: false }));
        setTimeout(async () => {
          if (previewContainerRef.current) {
            previewContainerRef.current.innerHTML = "";
            const previewer = init(previewContainerRef.current, {
              mode: "slide",
            });
            pptxPreviewerRef.current = previewer;
            await previewer.preview(arrayBuffer);
          }
        }, 0);
      } else if (fileType === "pdf") {
        const pdfBlobUrl = URL.createObjectURL(blob);
        currentBlobUrlRef.current = pdfBlobUrl;
        setPreviewModal((prev) => ({
          ...prev,
          isLoading: false,
          pdfBlobUrl,
        }));
      } else {
        throw new Error(`Preview not supported for file format: ${fileType}`);
      }
    } catch (err) {
      console.error("Preview render failed:", err);
      setPreviewModal((prev) => ({
        ...prev,
        isLoading: false,
        error:
          err.message ||
          "Failed to render document preview. The file can still be downloaded directly.",
      }));
    }
  };

  // Keyboard accessibility: Escape to close, focus trapping, cleanup
  useEffect(() => {
    if (!previewModal.isOpen) return;

    const handleKeyDown = (e) => {
      if (e.key === "Escape") {
        e.preventDefault();
        handleClosePreview();
        return;
      }

      if (e.key === "Tab" && modalRef.current) {
        const focusableElements = modalRef.current.querySelectorAll(
          'button, [href], input, select, textarea, [tabindex]:not([tabindex="-1"])'
        );
        if (focusableElements.length === 0) return;
        const firstEl = focusableElements[0];
        const lastEl = focusableElements[focusableElements.length - 1];

        if (e.shiftKey) {
          if (document.activeElement === firstEl) {
            e.preventDefault();
            lastEl.focus();
          }
        } else {
          if (document.activeElement === lastEl) {
            e.preventDefault();
            firstEl.focus();
          }
        }
      }
    };

    window.addEventListener("keydown", handleKeyDown);
    const focusTimer = setTimeout(() => {
      closeButtonRef.current?.focus();
    }, 50);

    return () => {
      window.removeEventListener("keydown", handleKeyDown);
      clearTimeout(focusTimer);
      document.body.style.overflow = "";
    };
  }, [previewModal.isOpen, handleClosePreview]);

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
                          <button
                            type="button"
                            onClick={() => handleOpenPreview(output, resultItem)}
                            className="preview-button"
                            aria-label={`Preview ${output.title}`}
                          >
                            Preview
                          </button>

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

      {/* Real Document Preview Modal */}
      {previewModal.isOpen && (
        <div
          className="preview-modal-overlay"
          onClick={(e) => {
            if (e.target === e.currentTarget) {
              handleClosePreview();
            }
          }}
          role="dialog"
          aria-modal="true"
          aria-labelledby="preview-modal-title"
        >
          <div className="preview-modal-window" ref={modalRef}>
            <header className="preview-modal-header">
              <div>
                <span className="preview-modal-badge">
                  {previewModal.fileType.toUpperCase()} PREVIEW
                </span>
                <h2 id="preview-modal-title">{previewModal.title}</h2>
              </div>

              <div className="preview-modal-header-actions">
                <a
                  href={previewModal.downloadUrl}
                  download
                  className="download-button preview-header-download"
                  target="_blank"
                  rel="noopener noreferrer"
                  style={{ textDecoration: "none" }}
                >
                  Download
                  <span>↓</span>
                </a>
                <button
                  type="button"
                  ref={closeButtonRef}
                  className="preview-modal-close"
                  onClick={handleClosePreview}
                  aria-label="Close preview"
                >
                  ✕
                </button>
              </div>
            </header>

            <div className="preview-modal-notice">
              <span>ℹ</span> In-browser preview rendering may differ slightly from native Word/PowerPoint layout. For full fidelity (two-column academic formatting, exact figures, and slide geometries), please download the file.
            </div>

            <div className="preview-modal-body">
              {previewModal.isLoading && (
                <div className="preview-loading-state">
                  <div className="preview-spinner"></div>
                  <p>
                    Loading and rendering {previewModal.fileType.toUpperCase()}{" "}
                    document...
                  </p>
                </div>
              )}

              {previewModal.error && (
                <div className="preview-error-state">
                  <div className="preview-error-icon">⚠️</div>
                  <h3>Unable to render in-browser preview</h3>
                  <p>{previewModal.error}</p>
                  <a
                    href={previewModal.downloadUrl}
                    download
                    className="download-button"
                    target="_blank"
                    rel="noopener noreferrer"
                    style={{
                      marginTop: "14px",
                      textDecoration: "none",
                      display: "inline-flex",
                    }}
                  >
                    Download instead
                    <span>↓</span>
                  </a>
                </div>
              )}

              {previewModal.fileType === "pdf" &&
                previewModal.pdfBlobUrl &&
                !previewModal.isLoading &&
                !previewModal.error && (
                  <iframe
                    src={previewModal.pdfBlobUrl}
                    title={`${previewModal.title} PDF Preview`}
                    className="preview-pdf-iframe"
                  />
                )}

              <div
                ref={previewContainerRef}
                className={`preview-render-container ${
                  previewModal.fileType === "pptx"
                    ? "pptx-container"
                    : "docx-container"
                }`}
                style={{
                  display:
                    previewModal.isLoading ||
                    previewModal.error ||
                    previewModal.fileType === "pdf"
                      ? "none"
                      : "block",
                }}
              />
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

export default Outputs;