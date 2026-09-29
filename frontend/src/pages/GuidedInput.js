import { useState } from "react";
import { useLocation, useNavigate } from "react-router-dom";
import { submitGuidedInputTier, composeDocuments } from "../api";
import "./GuidedInput.css";

function GuidedInput() {
  const navigate = useNavigate();
  const location = useLocation();

  const researchData = location.state || {};
  const sessionId = researchData.session_id;
  const topic = researchData.topic || "";

  const selectedOutputs = Array.isArray(researchData.selectedOutputs)
    ? researchData.selectedOutputs
    : [];

  const showPresentation = selectedOutputs.includes("ppt");
  const showAcademic = selectedOutputs.includes("research_paper");

  // Determine starting active tier
  const initialTier =
    researchData.nextTier &&
    (researchData.nextTier === "presentation_info" ||
      researchData.nextTier === "academic_info")
      ? researchData.nextTier
      : "cover_info";

  const [activeTier, setActiveTier] = useState(initialTier);
  const [completedTiers, setCompletedTiers] = useState([]);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [errorMessage, setErrorMessage] = useState(null);

  const [coverInfo, setCoverInfo] = useState({
    title: topic,
    subtitle: "",
    authors: "",
    institution: "",
    date: "",
  });

  const [presentationInfo, setPresentationInfo] = useState({
    problemStatement: "",
    techStack: "",
    architecture: "",
    results: "",
    timeline: "",
  });

  const [academicInfo, setAcademicInfo] = useState({
    methodology: "",
    dataset: "",
    tools: "",
    measured: "",
    results: "",
    limitations: "",
  });

  const hasResearchData = Boolean(sessionId) && selectedOutputs.length > 0;

  const updateCover = (field, value) => {
    setCoverInfo((current) => ({
      ...current,
      [field]: value,
    }));
  };

  const updatePresentation = (field, value) => {
    setPresentationInfo((current) => ({
      ...current,
      [field]: value,
    }));
  };

  const updateAcademic = (field, value) => {
    setAcademicInfo((current) => ({
      ...current,
      [field]: value,
    }));
  };

  // Helper to trigger compose and navigate
  const triggerComposeAndNavigate = async () => {
    try {
      await composeDocuments(sessionId);
      navigate("/research-progress", {
        state: {
          session_id: sessionId,
          topic,
          selectedOutputs,
          phase: "compose",
        },
      });
    } catch (err) {
      setErrorMessage(err.message || "Failed to trigger document composition.");
      setIsSubmitting(false);
    }
  };

  // ---------------------------------------------------------------------------
  // Tier Submissions
  // ---------------------------------------------------------------------------

  const handleSubmitCover = async (e) => {
    if (e) e.preventDefault();
    if (!coverInfo.title.trim() || isSubmitting) return;

    setIsSubmitting(true);
    setErrorMessage(null);

    const coverPayload = {
      title: coverInfo.title.trim(),
      subtitle: coverInfo.subtitle.trim() || null,
      authors: coverInfo.authors
        ? coverInfo.authors
            .split(",")
            .map((author) => author.trim())
            .filter(Boolean)
        : [],
      institution: coverInfo.institution.trim() || null,
      date: coverInfo.date.trim() || null,
    };

    try {
      const res = await submitGuidedInputTier(sessionId, "cover_info", coverPayload);

      if (!res.ok) {
        setErrorMessage(res.error || "Failed to validate cover information.");
        setIsSubmitting(false);
        return;
      }

      setCompletedTiers((prev) => Array.from(new Set([...prev, "cover_info"])));

      if (res.is_complete) {
        await triggerComposeAndNavigate();
      } else if (res.next_tier) {
        setActiveTier(res.next_tier);
        setIsSubmitting(false);
      } else {
        // Fallback check against selected outputs
        if (showPresentation && !completedTiers.includes("presentation_info")) {
          setActiveTier("presentation_info");
        } else if (showAcademic && !completedTiers.includes("academic_info")) {
          setActiveTier("academic_info");
        } else {
          await triggerComposeAndNavigate();
        }
        setIsSubmitting(false);
      }
    } catch (err) {
      setErrorMessage(err.message || "Network error submitting cover information.");
      setIsSubmitting(false);
    }
  };

  const handleSubmitPresentation = async (e) => {
    if (e) e.preventDefault();
    if (isSubmitting) return;

    if (
      !presentationInfo.problemStatement.trim() ||
      !presentationInfo.techStack.trim() ||
      !presentationInfo.architecture.trim() ||
      !presentationInfo.results.trim()
    ) {
      setErrorMessage(
        "Please fill in Problem Statement, Tech Stack, Architecture, and Results."
      );
      return;
    }

    setIsSubmitting(true);
    setErrorMessage(null);

    const presentationPayload = {
      problem_statement: presentationInfo.problemStatement.trim(),
      tech_stack: presentationInfo.techStack
        ? presentationInfo.techStack
            .split(",")
            .map((item) => item.trim())
            .filter(Boolean)
        : [],
      own_architecture_summary: presentationInfo.architecture.trim(),
      own_results_summary: presentationInfo.results.trim(),
      project_timeline: presentationInfo.timeline.trim() || null,
    };

    try {
      const res = await submitGuidedInputTier(
        sessionId,
        "presentation_info",
        presentationPayload
      );

      if (!res.ok) {
        setErrorMessage(res.error || "Failed to validate presentation information.");
        setIsSubmitting(false);
        return;
      }

      setCompletedTiers((prev) =>
        Array.from(new Set([...prev, "presentation_info"]))
      );

      if (res.is_complete) {
        await triggerComposeAndNavigate();
      } else if (res.next_tier) {
        setActiveTier(res.next_tier);
        setIsSubmitting(false);
      } else {
        if (showAcademic && !completedTiers.includes("academic_info")) {
          setActiveTier("academic_info");
        } else {
          await triggerComposeAndNavigate();
        }
        setIsSubmitting(false);
      }
    } catch (err) {
      setErrorMessage(
        err.message || "Network error submitting presentation information."
      );
      setIsSubmitting(false);
    }
  };

  const handleSubmitAcademic = async (e) => {
    if (e) e.preventDefault();
    if (isSubmitting) return;

    if (
      !academicInfo.methodology.trim() ||
      !academicInfo.dataset.trim() ||
      !academicInfo.tools.trim() ||
      !academicInfo.measured.trim() ||
      !academicInfo.results.trim()
    ) {
      setErrorMessage(
        "Please fill in Methodology, Dataset, Tools, What Was Measured, and Key Results."
      );
      return;
    }

    setIsSubmitting(true);
    setErrorMessage(null);

    const academicPayload = {
      methodology: academicInfo.methodology.trim(),
      dataset_or_sample: academicInfo.dataset.trim(),
      tools_used: academicInfo.tools
        ? academicInfo.tools
            .split(",")
            .map((item) => item.trim())
            .filter(Boolean)
        : [],
      what_was_measured: academicInfo.measured.trim(),
      key_results: academicInfo.results.trim(),
      limitations: academicInfo.limitations.trim() || null,
    };

    try {
      const res = await submitGuidedInputTier(
        sessionId,
        "academic_info",
        academicPayload
      );

      if (!res.ok) {
        setErrorMessage(res.error || "Failed to validate academic content.");
        setIsSubmitting(false);
        return;
      }

      setCompletedTiers((prev) =>
        Array.from(new Set([...prev, "academic_info"]))
      );

      if (res.is_complete) {
        await triggerComposeAndNavigate();
      } else if (res.next_tier) {
        setActiveTier(res.next_tier);
        setIsSubmitting(false);
      } else {
        await triggerComposeAndNavigate();
      }
    } catch (err) {
      setErrorMessage(err.message || "Network error submitting academic content.");
      setIsSubmitting(false);
    }
  };

  /*
   * If the user opens /guided-input directly without session state
   */
  if (!hasResearchData) {
    return (
      <div className="guided-page">
        <div className="guided-background-glow"></div>

        <header className="guided-header">
          <div className="guided-logo">
            <span>✦</span>
            ResearchAI
          </div>
        </header>

        <main className="guided-container">
          <div className="guided-empty-state">
            <div className="guided-empty-icon">!</div>

            <h1>
              No research project
              <br />
              <span>was selected.</span>
            </h1>

            <p>
              Please start a new research project and select deliverables before
              opening Guided Input.
            </p>

            <button
              type="button"
              className="start-research-button"
              onClick={() => navigate("/research")}
            >
              Start a Research Project
              <span>→</span>
            </button>
          </div>
        </main>
      </div>
    );
  }

  return (
    <div className="guided-page">
      <div className="guided-background-glow"></div>

      {/* Header */}
      <header className="guided-header">
        <div className="guided-logo">
          <span>✦</span>
          ResearchAI
        </div>

        <button
          type="button"
          className="back-button"
          onClick={() =>
            navigate("/research-results", {
              state: { session_id: sessionId, topic },
            })
          }
        >
          ← Back to Results
        </button>
      </header>

      {/* Main Container */}
      <main className="guided-container">
        {/* Heading */}
        <div className="guided-heading">
          <div className="guided-eyebrow">
            <span></span>
            RESEARCH CONFIGURATION
          </div>

          <h1>
            Tell us about your
            <br />
            <span>research project.</span>
          </h1>

          <p>
            Provide details for each required section so our agents can compose
            grounded, personalized deliverables.
          </p>
        </div>

        {/* Stepper Progress */}
        <div className="guided-progress">
          <div
            className={`progress-step ${
              activeTier === "cover_info"
                ? "active"
                : completedTiers.includes("cover_info")
                ? "completed"
                : ""
            }`}
            onClick={() => setActiveTier("cover_info")}
            style={{ cursor: "pointer" }}
          >
            <span>01</span>
            Cover Information {completedTiers.includes("cover_info") && "✓"}
          </div>

          {showPresentation && (
            <div
              className={`progress-step ${
                activeTier === "presentation_info"
                  ? "active"
                  : completedTiers.includes("presentation_info")
                  ? "completed"
                  : ""
              }`}
              onClick={() => setActiveTier("presentation_info")}
              style={{ cursor: "pointer" }}
            >
              <span>02</span>
              Presentation {completedTiers.includes("presentation_info") && "✓"}
            </div>
          )}

          {showAcademic && (
            <div
              className={`progress-step ${
                activeTier === "academic_info"
                  ? "active"
                  : completedTiers.includes("academic_info")
                  ? "completed"
                  : ""
              }`}
              onClick={() => setActiveTier("academic_info")}
              style={{ cursor: "pointer" }}
            >
              <span>{showPresentation ? "03" : "02"}</span>
              Academic Content {completedTiers.includes("academic_info") && "✓"}
            </div>
          )}
        </div>

        {/* Global Error Banner */}
        {errorMessage && (
          <div
            style={{
              padding: "14px 18px",
              backgroundColor: "rgba(239, 68, 68, 0.12)",
              border: "1px solid rgba(239, 68, 68, 0.3)",
              borderRadius: "10px",
              color: "#f87171",
              fontSize: "14px",
              marginBottom: "20px",
            }}
          >
            ⚠️ {errorMessage}
          </div>
        )}

        {/* Section 1: Cover Information */}
        {activeTier === "cover_info" && (
          <section className="guided-card">
            <div className="card-heading">
              <div className="card-number">01</div>

              <div>
                <h2>Cover Information</h2>
                <p>Basic information used across your generated documents.</p>
              </div>

              <span className="required-label">REQUIRED</span>
            </div>

            <div className="form-grid">
              <div className="form-group full-width">
                <label>Research Title</label>
                <input
                  type="text"
                  value={coverInfo.title}
                  onChange={(event) => updateCover("title", event.target.value)}
                  placeholder="Enter your research title"
                />
              </div>

              <div className="form-group">
                <label>Subtitle</label>
                <input
                  type="text"
                  value={coverInfo.subtitle}
                  onChange={(event) =>
                    updateCover("subtitle", event.target.value)
                  }
                  placeholder="Optional subtitle"
                />
              </div>

              <div className="form-group">
                <label>Authors</label>
                <input
                  type="text"
                  value={coverInfo.authors}
                  onChange={(event) =>
                    updateCover("authors", event.target.value)
                  }
                  placeholder="e.g. Sneha Konade, Student 2"
                />
              </div>

              <div className="form-group">
                <label>Institution</label>
                <input
                  type="text"
                  value={coverInfo.institution}
                  onChange={(event) =>
                    updateCover("institution", event.target.value)
                  }
                  placeholder="College / University"
                />
              </div>

              <div className="form-group">
                <label>Date</label>
                <input
                  type="text"
                  value={coverInfo.date}
                  onChange={(event) => updateCover("date", event.target.value)}
                  placeholder="e.g. September 2026"
                />
              </div>
            </div>

            <div className="guided-footer" style={{ marginTop: "24px" }}>
              <div className="guided-status">
                <span className="agent-status"></span>
                Step 1 of {1 + (showPresentation ? 1 : 0) + (showAcademic ? 1 : 0)}
              </div>

              <button
                type="button"
                className="start-research-button"
                onClick={handleSubmitCover}
                disabled={!coverInfo.title.trim() || isSubmitting}
              >
                {isSubmitting
                  ? "Saving..."
                  : showPresentation || showAcademic
                  ? "Save & Continue"
                  : "Save & Generate Deliverables"}
                <span>→</span>
              </button>
            </div>
          </section>
        )}

        {/* Section 2: Presentation Information */}
        {showPresentation && activeTier === "presentation_info" && (
          <section className="guided-card">
            <div className="card-heading">
              <div className="card-number">02</div>

              <div>
                <h2>Project Presentation</h2>
                <p>Information needed to create your presentation deck.</p>
              </div>

              <span className="required-label">PPT SELECTED</span>
            </div>

            <div className="form-grid">
              <div className="form-group full-width">
                <label>Problem Statement</label>
                <textarea
                  rows="3"
                  value={presentationInfo.problemStatement}
                  onChange={(event) =>
                    updatePresentation("problemStatement", event.target.value)
                  }
                  placeholder="What core problem or challenge does this research address?"
                />
              </div>

              <div className="form-group">
                <label>Tech Stack</label>
                <input
                  type="text"
                  value={presentationInfo.techStack}
                  onChange={(event) =>
                    updatePresentation("techStack", event.target.value)
                  }
                  placeholder="e.g. Python, PyTorch, LangChain"
                />
              </div>

              <div className="form-group">
                <label>Project Timeline</label>
                <input
                  type="text"
                  value={presentationInfo.timeline}
                  onChange={(event) =>
                    updatePresentation("timeline", event.target.value)
                  }
                  placeholder="e.g. Q3 2026"
                />
              </div>

              <div className="form-group full-width">
                <label>Architecture Summary</label>
                <textarea
                  rows="3"
                  value={presentationInfo.architecture}
                  onChange={(event) =>
                    updatePresentation("architecture", event.target.value)
                  }
                  placeholder="Describe your system or project architecture."
                />
              </div>

              <div className="form-group full-width">
                <label>Results Summary</label>
                <textarea
                  rows="3"
                  value={presentationInfo.results}
                  onChange={(event) =>
                    updatePresentation("results", event.target.value)
                  }
                  placeholder="Summarize your experimental results or project outcomes."
                />
              </div>
            </div>

            <div className="guided-footer" style={{ marginTop: "24px" }}>
              <div className="guided-status">
                <span className="agent-status"></span>
                Step {1 + 1} of {1 + (showPresentation ? 1 : 0) + (showAcademic ? 1 : 0)}
              </div>

              <button
                type="button"
                className="start-research-button"
                onClick={handleSubmitPresentation}
                disabled={isSubmitting}
              >
                {isSubmitting
                  ? "Saving..."
                  : showAcademic
                  ? "Save & Continue"
                  : "Save & Generate Deliverables"}
                <span>→</span>
              </button>
            </div>
          </section>
        )}

        {/* Section 3: Academic Content */}
        {showAcademic && activeTier === "academic_info" && (
          <section className="guided-card">
            <div className="card-heading">
              <div className="card-number">
                {showPresentation ? "03" : "02"}
              </div>

              <div>
                <h2>Academic Content</h2>
                <p>Information required to format your formal research paper.</p>
              </div>

              <span className="required-label">RESEARCH PAPER</span>
            </div>

            <div className="form-grid">
              <div className="form-group full-width">
                <label>Methodology</label>
                <textarea
                  rows="3"
                  value={academicInfo.methodology}
                  onChange={(event) =>
                    updateAcademic("methodology", event.target.value)
                  }
                  placeholder="Describe the methodology used in your research."
                />
              </div>

              <div className="form-group">
                <label>Dataset / Sample</label>
                <textarea
                  rows="3"
                  value={academicInfo.dataset}
                  onChange={(event) =>
                    updateAcademic("dataset", event.target.value)
                  }
                  placeholder="Describe your dataset or sample."
                />
              </div>

              <div className="form-group">
                <label>Tools Used</label>
                <textarea
                  rows="3"
                  value={academicInfo.tools}
                  onChange={(event) =>
                    updateAcademic("tools", event.target.value)
                  }
                  placeholder="e.g. Python, React, FastAPI"
                />
              </div>

              <div className="form-group">
                <label>What Was Measured?</label>
                <textarea
                  rows="3"
                  value={academicInfo.measured}
                  onChange={(event) =>
                    updateAcademic("measured", event.target.value)
                  }
                  placeholder="What metrics, outcomes, or variables were measured?"
                />
              </div>

              <div className="form-group">
                <label>Key Results</label>
                <textarea
                  rows="3"
                  value={academicInfo.results}
                  onChange={(event) =>
                    updateAcademic("results", event.target.value)
                  }
                  placeholder="Enter your actual research results."
                />
              </div>

              <div className="form-group full-width">
                <label>Limitations</label>
                <textarea
                  rows="3"
                  value={academicInfo.limitations}
                  onChange={(event) =>
                    updateAcademic("limitations", event.target.value)
                  }
                  placeholder="Optional limitations of your research."
                />
              </div>
            </div>

            <div className="guided-footer" style={{ marginTop: "24px" }}>
              <div className="guided-status">
                <span className="agent-status"></span>
                Final Step of {1 + (showPresentation ? 1 : 0) + (showAcademic ? 1 : 0)}
              </div>

              <button
                type="button"
                className="start-research-button"
                onClick={handleSubmitAcademic}
                disabled={isSubmitting}
              >
                {isSubmitting ? "Generating Deliverables..." : "Complete & Generate Deliverables"}
                <span>→</span>
              </button>
            </div>
          </section>
        )}
      </main>
    </div>
  );
}

export default GuidedInput;