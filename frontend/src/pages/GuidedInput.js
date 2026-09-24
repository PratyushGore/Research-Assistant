import { useLocation, useNavigate } from "react-router-dom";
import { useState } from "react";
import "./GuidedInput.css";

function GuidedInput() {
  const navigate = useNavigate();
  const location = useLocation();

  const researchData = location.state || {};

  const topic = researchData.topic || "";

  const selectedOutputs = Array.isArray(
    researchData.selectedOutputs
  )
    ? researchData.selectedOutputs
    : [];

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

  const showPresentation =
    selectedOutputs.includes("ppt");

  const showAcademic =
    selectedOutputs.includes("research_paper");

  const hasResearchData =
    Boolean(topic) && selectedOutputs.length > 0;

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

  const handleStartResearch = () => {
    const guidedInput = {
      coverInfo: {
        title: coverInfo.title,
        subtitle: coverInfo.subtitle || null,

        authors: coverInfo.authors
          ? coverInfo.authors
              .split(",")
              .map((author) => author.trim())
              .filter(Boolean)
          : [],

        institution: coverInfo.institution || null,
        date: coverInfo.date || null,
      },

      projectPresentationInfo: showPresentation
        ? {
            problem_statement:
              presentationInfo.problemStatement,

            tech_stack:
              presentationInfo.techStack
                ? presentationInfo.techStack
                    .split(",")
                    .map((item) => item.trim())
                    .filter(Boolean)
                : [],

            own_architecture_summary:
              presentationInfo.architecture,

            own_results_summary:
              presentationInfo.results,

            project_timeline:
              presentationInfo.timeline || null,
          }
        : null,

      academicContentInfo: showAcademic
        ? {
            methodology:
              academicInfo.methodology,

            dataset_or_sample:
              academicInfo.dataset,

            tools_used:
              academicInfo.tools
                ? academicInfo.tools
                    .split(",")
                    .map((item) => item.trim())
                    .filter(Boolean)
                : [],

            what_was_measured:
              academicInfo.measured,

            key_results:
              academicInfo.results,

            limitations:
              academicInfo.limitations || null,
          }
        : null,
    };

    console.log("Research Topic:", topic);
    console.log(
      "Selected Outputs:",
      selectedOutputs
    );
    console.log(
      "Guided Input:",
      guidedInput
    );

    navigate("/research-progress", {
      state: {
        topic,
        selectedOutputs,
        guidedInput,
      },
    });
  };

  /*
   * If the user opens /guided-input directly
   * without coming from Research Setup.
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

            <div className="guided-empty-icon">
              !
            </div>

            <h1>
              No research project
              <br />
              <span>was selected.</span>
            </h1>

            <p>
              Please start a new research project
              before opening the Guided Input page.
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
          onClick={() => navigate("/research")}
        >
          ← Back
        </button>

      </header>

      {/* Main */}
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
            Provide a few details so our agents can
            create accurate, personalized research
            outputs.
          </p>

        </div>

        {/* Progress */}
        <div className="guided-progress">

          <div className="progress-step active">
            <span>01</span>
            Cover Information
          </div>

          {showPresentation && (
            <div className="progress-step active">
              <span>02</span>
              Presentation
            </div>
          )}

          {showAcademic && (
            <div className="progress-step active">
              <span>
                {showPresentation ? "03" : "02"}
              </span>
              Academic Content
            </div>
          )}

        </div>

        {/* Cover Information */}
        <section className="guided-card">

          <div className="card-heading">

            <div className="card-number">
              01
            </div>

            <div>
              <h2>
                Cover Information
              </h2>

              <p>
                Basic information used across
                your generated documents.
              </p>
            </div>

            <span className="required-label">
              REQUIRED
            </span>

          </div>

          <div className="form-grid">

            <div className="form-group full-width">

              <label>
                Research Title
              </label>

              <input
                type="text"
                value={coverInfo.title}
                onChange={(event) =>
                  updateCover(
                    "title",
                    event.target.value
                  )
                }
                placeholder="Enter your research title"
              />

            </div>

            <div className="form-group">

              <label>
                Subtitle
              </label>

              <input
                type="text"
                value={coverInfo.subtitle}
                onChange={(event) =>
                  updateCover(
                    "subtitle",
                    event.target.value
                  )
                }
                placeholder="Optional subtitle"
              />

            </div>

            <div className="form-group">

              <label>
                Authors
              </label>

              <input
                type="text"
                value={coverInfo.authors}
                onChange={(event) =>
                  updateCover(
                    "authors",
                    event.target.value
                  )
                }
                placeholder="e.g. Sneha Konade, Student 2"
              />

            </div>

            <div className="form-group">

              <label>
                Institution
              </label>

              <input
                type="text"
                value={coverInfo.institution}
                onChange={(event) =>
                  updateCover(
                    "institution",
                    event.target.value
                  )
                }
                placeholder="College / University"
              />

            </div>

            <div className="form-group">

              <label>
                Date
              </label>

              <input
                type="text"
                value={coverInfo.date}
                onChange={(event) =>
                  updateCover(
                    "date",
                    event.target.value
                  )
                }
                placeholder="e.g. September 2026"
              />

            </div>

          </div>

        </section>

        {/* Presentation Information */}
        {showPresentation && (
          <section className="guided-card">

            <div className="card-heading">

              <div className="card-number">
                02
              </div>

              <div>
                <h2>
                  Project Presentation
                </h2>

                <p>
                  Information needed to create
                  your presentation.
                </p>
              </div>

              <span className="required-label">
                PPT SELECTED
              </span>

            </div>

            <div className="form-grid">

              <div className="form-group full-width">

                <label>
                  Problem Statement
                </label>

                <textarea
                  rows="4"
                  value={
                    presentationInfo.problemStatement
                  }
                  onChange={(event) =>
                    updatePresentation(
                      "problemStatement",
                      event.target.value
                    )
                  }
                  placeholder="What problem does your project solve?"
                />

              </div>

              <div className="form-group">

                <label>
                  Technology Stack
                </label>

                <textarea
                  rows="3"
                  value={
                    presentationInfo.techStack
                  }
                  onChange={(event) =>
                    updatePresentation(
                      "techStack",
                      event.target.value
                    )
                  }
                  placeholder="e.g. React, FastAPI, LangGraph..."
                />

              </div>

              <div className="form-group">

                <label>
                  Architecture Summary
                </label>

                <textarea
                  rows="3"
                  value={
                    presentationInfo.architecture
                  }
                  onChange={(event) =>
                    updatePresentation(
                      "architecture",
                      event.target.value
                    )
                  }
                  placeholder="Briefly describe your system architecture."
                />

              </div>

              <div className="form-group full-width">

                <label>
                  Own Results Summary
                </label>

                <textarea
                  rows="4"
                  value={
                    presentationInfo.results
                  }
                  onChange={(event) =>
                    updatePresentation(
                      "results",
                      event.target.value
                    )
                  }
                  placeholder="Describe your project's actual results or current findings."
                />

              </div>

              <div className="form-group full-width">

                <label>
                  Project Timeline
                </label>

                <input
                  type="text"
                  value={
                    presentationInfo.timeline
                  }
                  onChange={(event) =>
                    updatePresentation(
                      "timeline",
                      event.target.value
                    )
                  }
                  placeholder="Optional project timeline"
                />

              </div>

            </div>

          </section>
        )}

        {/* Academic Information */}
        {showAcademic && (
          <section className="guided-card">

            <div className="card-heading">

              <div className="card-number">
                {showPresentation ? "03" : "02"}
              </div>

              <div>
                <h2>
                  Academic Content
                </h2>

                <p>
                  Information required for
                  the research paper.
                </p>
              </div>

              <span className="required-label">
                PAPER SELECTED
              </span>

            </div>

            <div className="form-grid">

              <div className="form-group full-width">

                <label>
                  Methodology
                </label>

                <textarea
                  rows="4"
                  value={
                    academicInfo.methodology
                  }
                  onChange={(event) =>
                    updateAcademic(
                      "methodology",
                      event.target.value
                    )
                  }
                  placeholder="Describe the methodology used in your research."
                />

              </div>

              <div className="form-group">

                <label>
                  Dataset / Sample
                </label>

                <textarea
                  rows="3"
                  value={
                    academicInfo.dataset
                  }
                  onChange={(event) =>
                    updateAcademic(
                      "dataset",
                      event.target.value
                    )
                  }
                  placeholder="Describe your dataset or sample."
                />

              </div>

              <div className="form-group">

                <label>
                  Tools Used
                </label>

                <textarea
                  rows="3"
                  value={
                    academicInfo.tools
                  }
                  onChange={(event) =>
                    updateAcademic(
                      "tools",
                      event.target.value
                    )
                  }
                  placeholder="e.g. Python, React, FastAPI"
                />

              </div>

              <div className="form-group">

                <label>
                  What Was Measured?
                </label>

                <textarea
                  rows="3"
                  value={
                    academicInfo.measured
                  }
                  onChange={(event) =>
                    updateAcademic(
                      "measured",
                      event.target.value
                    )
                  }
                  placeholder="What metrics, outcomes, or variables were measured?"
                />

              </div>

              <div className="form-group">

                <label>
                  Key Results
                </label>

                <textarea
                  rows="3"
                  value={
                    academicInfo.results
                  }
                  onChange={(event) =>
                    updateAcademic(
                      "results",
                      event.target.value
                    )
                  }
                  placeholder="Enter your actual research results."
                />

              </div>

              <div className="form-group full-width">

                <label>
                  Limitations
                </label>

                <textarea
                  rows="3"
                  value={
                    academicInfo.limitations
                  }
                  onChange={(event) =>
                    updateAcademic(
                      "limitations",
                      event.target.value
                    )
                  }
                  placeholder="Optional limitations of your research."
                />

              </div>

            </div>

          </section>
        )}

        {/* Footer */}
        <div className="guided-footer">

          <div className="guided-status">
            <span className="agent-status"></span>

            Your information stays within this research session.
          </div>

          <button
            type="button"
            className="start-research-button"
            onClick={handleStartResearch}
            disabled={!coverInfo.title.trim()}
          >
            Start Research

            <span>→</span>
          </button>

        </div>

      </main>
    </div>
  );
}

export default GuidedInput;