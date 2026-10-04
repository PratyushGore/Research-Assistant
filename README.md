# Multi-Agent AI Research & Publication Assistant

A multi-agent academic research assistant that orchestrates automated paper discovery, PDF ingestion, cross-paper summarization, claim-level fact verification, citation formatting, student-guided synthesis, and multi-format document publication. Built with FastAPI, LangGraph, ChromaDB, Google Gemini, and a responsive React frontend, the system transforms open academic literature into publication-ready research deliverables with verifiable grounding and citation transparency.

---

## Key Features

- **Deterministic Academic Search**: Queries Semantic Scholar, arXiv, and CORE with query caching, multi-source deduplication, and a configurable paper limit (3 to 15 papers). If fewer candidate papers meet criteria, the system automatically detects this and provides clear UI notification.
- **Robust Document Ingestion & Vector Storage**: Downloads open-access full-text PDFs with configurable size limits (default 2 MB) and timeouts, segments documents using PyMuPDF into section-aware chunks, and indexes them into ChromaDB using SentenceTransformers embeddings.
- **Two-Stage Summarization**: Performs individual per-paper summary and empirical claim extraction, followed by a multi-paper cross-synthesis identifying consensus, contrasting methodologies, and research gaps.
- **Claim-Level Grounding & Verification**: Evaluates extracted empirical claims against raw paper source chunks using multi-worker parallel LLM verification, scoring confidence and detecting unsupported assertions or contradictions.
- **Automated Citation Formatting**: Generates verified bibliography entries and corresponding in-text citation markers supporting IEEE and APA referencing styles.
- **Always-On Grounded Q&A**: Standalone chat assistant (`qa_graph`) allowing users to ask natural language questions grounded strictly in the ingested research papers and verified findings.
- **Three-Tier Guided Input Intake**: Collects student project context—including cover details, technical architecture, and methodology/results—to tailor final documents.
- **Four High-Fidelity Deliverables**:
  1. **Presentation Deck (PPTX)**: Widescreen 16:9 slides with professional color themes, structured problem statements, technical architecture, results, and speaker notes.
  2. **Research Paper (DOCX / PDF)**: Academic structure (Abstract, Introduction, Related Work, Methodology, Findings, References) in Word and ReportLab PDF formats.
  3. **Literature Survey (DOCX / PDF)**: Systematic comparative literature analysis grouping related works, benchmarking findings, and highlighting open challenges.
  4. **Executive Summary (DOCX / PDF)**: Concise overview summarizing key discoveries, methodology, and actionable takeaways for non-specialist stakeholders.
- **Interactive Web Interface**: React SPA featuring real-time WebSocket progress tracking, collapsible paper summaries, claim verification badges, live deliverable previews, and direct file downloads.

---

## Pipeline Architecture

The system coordinates research discovery and document composition via decoupled LangGraph state graphs communicating through an in-memory session manager and streaming status via WebSockets.

```mermaid
flowchart TD
    subgraph Frontend["React CRA Frontend (Port 3000)"]
        UI_Setup["1. Research Setup<br/>(Topic + Paper Count 3-15)"]
        UI_Progress["2. Live WebSocket Monitor<br/>& Paper Viewer"]
        UI_QA["Interactive Grounded<br/>Q&A Assistant"]
        UI_Guided["3. Guided Input Intake<br/>(Tiers 1-3)"]
        UI_Outputs["4. Deliverable Selection,<br/>Preview & Download"]
    end

    subgraph Backend["FastAPI Orchestration Layer (Port 8000)"]
        API["FastAPI REST Endpoints<br/>(Sessions & Deliverables)"]
        WS["WebSocket Streamer<br/>(/ws/research/{session_id})"]
        Session["Session Store<br/>(In-Memory State Machine)"]
    end

    subgraph ResearchPipeline["Research Graph (LangGraph)"]
        R_START([START]) --> Search["Search Agent<br/>(Semantic Scholar, arXiv, CORE)"]
        Search --> Ingestion["Ingestion Agent<br/>(PyMuPDF Chunking & Caching)"]
        Ingestion --> ChromaDB[("ChromaDB Vector Store<br/>(SentenceTransformers)")]
        Ingestion --> Summarization["Summarization Agent<br/>(Per-Paper & Synthesis)"]
        Summarization --> Verification["Verification Agent<br/>(Claim Grounding & Contradictions)"]
        Verification --> Citation["Citation Agent<br/>(IEEE / APA Citation Styles)"]
        Citation --> R_END([END: Findings Packet])
    end

    subgraph QAPipeline["Interactive QA Graph"]
        QA_START([START]) --> UserQA["User Q&A Agent<br/>(Retrieval over chunks & findings)"] --> QA_END([END])
    end

    subgraph ComposePipeline["Composition & Render Pipeline (LangGraph)"]
        C_START([START]) --> GuidedInput["Guided Input Intake<br/>(Cover, deck & methodology info)"]
        GuidedInput --> FanOut{"Route to Deliverables"}
        FanOut --> Comp_LS["Literature Survey Composer"]
        FanOut --> Comp_ES["Executive Summary Composer"]
        FanOut --> Comp_PPT["Presentation PPT Composer"]
        FanOut --> Comp_RP["Research Paper Composer"]
        Comp_LS --> Renderers["Output Renderers<br/>(python-docx, python-pptx, reportlab)"]
        Comp_ES --> Renderers
        Comp_PPT --> Renderers
        Comp_RP --> Renderers
        Renderers --> C_END([Generated Files Stored])
    end

    UI_Setup -->|POST /api/research/start| API
    API --> Session
    Session --> ResearchPipeline
    ResearchPipeline -.->|Stage progress & events| WS -.-> UI_Progress
    UI_QA <-->|POST /api/qa| API <--> QAPipeline
    UI_Guided -->|POST /api/research/{id}/guided-input/tier{n}| API
    UI_Outputs -->|POST /api/research/{id}/generate-outputs| API
    API --> ComposePipeline
    ComposePipeline -.->|Generated files & preview| UI_Outputs
```

---

## Deliverables & Paper Selection Strategy

### Deliverable Types
1. **Presentation Slides (`.pptx`)**: Generates 16:9 widescreen presentation decks using themed layout templates, structured bullet points, student architecture summaries, and automated speaker notes.
2. **Research Paper (`.docx`, `.pdf`)**: Formal academic publication structure containing Title, Abstract, Introduction, Literature Review, Methodology, Analysis, Discussion, and Reference Bibliography.
3. **Literature Survey (`.docx`, `.pdf`)**: Systematic taxonomy and comparative synthesis analyzing commonalities, divergences, and open research directions across the gathered corpus.
4. **Executive Summary (`.docx`, `.pdf`)**: High-impact synthesis distilling key research contributions, critical findings, and practical takeaways.

### Paper Selection Strategy
- **User-Selected Paper Count**: The user selects a target paper count between 3 and 15 (default: 8) during the setup step.
- **Deterministic Search**: Searches query Semantic Scholar, arXiv, and CORE with fixed-seed relevance ranking and local file-based search caching to ensure reproducible paper selection across runs.
- **Graceful Under-count Notification**: If the academic repositories return fewer valid open-access candidate papers than the requested target, the pipeline proceeds with all available papers and notifies the user via `paper_notice` in the UI (e.g., *"Requested 12 papers, but only 7 available from academic sources for this topic"*).

---

## Tech Stack

- **Backend Runtime**: Python 3.11+
- **API & Streaming**: FastAPI, Uvicorn, WebSockets, Pydantic v2
- **Orchestration & Workflows**: LangGraph, LangChain Core
- **LLM Engine**: Google Gemini API (`google-generativeai`, `gemini-3.5-flash-lite`)
- **Vector Store & Embeddings**: ChromaDB, Sentence-Transformers (`all-MiniLM-L6-v2`)
- **Document Processing**: PyMuPDF (`fitz`), Requests
- **Document Generation**: `python-docx` (Word), `python-pptx` (PowerPoint), `reportlab` (PDF)
- **Frontend**: React 18 (Create React App), Vanilla CSS
- **Testing**: `pytest`, `fastapi.testclient` (`httpx`), Jest, React Testing Library

---

## Repository Structure

```
Research-Assistant/
├── .env.example                     # Reference environment variables
├── .gitignore                        # Git ignore patterns
├── README.md                         # Project documentation
├── requirements.txt                  # Production runtime dependencies
├── requirements-dev.txt              # Testing and development dependencies
├── docs/
│   ├── assumptions.md                # Project assumptions and design decisions
│   └── team_notes.md                 # Internal team notes and model reference guide
├── backend/
│   ├── main.py                       # FastAPI application entrypoint and routes
│   ├── orchestrator/
│   │   ├── __init__.py
│   │   ├── graph.py                  # LangGraph pipeline definition & state graphs
│   │   └── session.py                # Session store and lifecycle management
│   ├── schemas/
│   │   ├── __init__.py
│   │   └── schemas.py                # Pydantic data models and contracts
│   ├── vectorstore/
│   │   ├── __init__.py
│   │   └── store.py                  # ChromaDB vector store integration
│   └── agents/
│       ├── common/
│       │   ├── __init__.py
│       │   └── llm_client.py         # Gemini API client with caching
│       ├── search/
│       │   ├── __init__.py
│       │   └── agent.py              # S2, arXiv, and CORE paper search
│       ├── ingestion/
│       │   ├── __init__.py
│       │   └── agent.py              # PDF download, PyMuPDF parsing & chunking
│       ├── summarization/
│       │   ├── __init__.py
│       │   └── agent.py              # Per-paper and cross-paper LLM synthesis
│       ├── verification/
│       │   ├── __init__.py
│       │   └── agent.py              # Claim verification and contradiction detection
│       ├── citation/
│       │   ├── __init__.py
│       │   ├── agent.py              # Citation generation and formatting
│       │   └── formatter.py          # IEEE and APA formatters
│       ├── guided_input/
│       │   ├── __init__.py
│       │   ├── agent.py              # Intake flow for user project context
│       │   └── mapper.py             # Form data to GuidedInputBundle mapper
│       ├── user_qa/
│       │   ├── __init__.py
│       │   └── agent.py              # Grounded interactive Q&A assistant
│       ├── composer/
│       │   ├── __init__.py
│       │   ├── agent.py              # Document content composers
│       │   ├── doc_content.py        # Long-form structured document generation
│       │   ├── generator.py          # Markdown generator
│       │   ├── ppt_content.py        # Presentation slide generator
│       │   └── templates.py          # Deliverable outline templates
│       └── output_renderer/
│           ├── __init__.py
│           ├── docx_renderer.py      # Word document renderer
│           ├── pdf_renderer.py       # ReportLab PDF renderer
│           ├── pptx_renderer.py      # PowerPoint slide deck renderer
│           ├── renderer.py           # Unified renderer coordinator
│           └── theme.py              # PPT slide presentation styling themes
├── frontend/
│   ├── package.json                  # Frontend dependencies and scripts
│   ├── README.md                     # Frontend documentation
│   ├── public/                       # Static public assets
│   └── src/
│       ├── App.js                    # Application root & step routing
│       ├── api.js                    # Centralized API and WebSocket client
│       ├── index.js                  # React DOM mount point
│       └── pages/
│           ├── ResearchSetup.js      # Topic input and paper count selection
│           ├── ResearchResults.js    # Live progress, paper list, and Q&A
│           └── Outputs.js            # Guided intake, preview, and downloads
└── tests/
    ├── api/
    │   ├── __init__.py
    │   └── test_api.py               # REST API and WebSocket test suite
    ├── orchestrator/
    │   ├── __init__.py
    │   ├── test_graph_routing.py     # LangGraph node routing tests
    │   └── test_session.py           # Session store lifecycle tests
    ├── schemas/
    │   ├── __init__.py
    │   └── test_structured_content.py# Pydantic schema validation tests
    └── agents/
        ├── search/
        │   ├── __init__.py
        │   ├── test_deterministic_search_pipeline.py
        │   ├── test_pipeline_search_adapter.py
        │   └── test_search_agent.py
        ├── ingestion/
        │   ├── __init__.py
        │   ├── test_ingestion_agent.py
        │   ├── test_ingestion_chunk_ids.py
        │   ├── test_ingestion_download_limits.py
        │   └── test_ingestion_vectorstore_integration.py
        ├── summarization/
        │   ├── __init__.py
        │   └── test_summarization_verification_standalone.py
        ├── verification/
        │   ├── __init__.py
        │   ├── test_accuracy_harness.py
        │   ├── test_contradiction_quality.py
        │   └── test_verification_batched.py
        ├── vectorstore/
        │   ├── __init__.py
        │   └── test_vectorstore.py
        ├── citation/
        │   ├── __init__.py
        │   ├── test_agent.py
        │   └── test_formatter.py
        ├── guided_input/
        │   ├── __init__.py
        │   ├── test_agent_flow.py
        │   ├── test_mapper.py
        │   └── test_tiers.py
        ├── composer/
        │   ├── __init__.py
        │   ├── test_agent.py
        │   ├── test_doc_content.py
        │   ├── test_generator.py
        │   ├── test_ppt_content.py
        │   └── test_templates.py
        ├── output_renderer/
        │   ├── __init__.py
        │   ├── test_docx_renderer.py
        │   ├── test_pdf_renderer.py
        │   ├── test_pptx_renderer.py
        │   ├── test_renderer.py
        │   └── test_theme.py
        └── user_qa/
            ├── __init__.py
            └── test_agent.py
```

---

## Installation & Setup

### Prerequisites
- Python 3.11+
- Node.js 18+ and npm
- A Google Gemini API key ([Google AI Studio](https://aistudio.google.com/))

### 1. Backend Setup

```bash
# Clone the repository
git clone <repository-url>
cd Research-Assistant

# Create and activate a Python virtual environment
python -m venv venv
# On Windows PowerShell:
.\venv\Scripts\Activate.ps1
# On macOS/Linux:
source venv/bin/activate

# Install runtime dependencies
pip install -r requirements.txt

# Configure environment variables
cp .env.example .env
# Edit .env and supply your GEMINI_API_KEY
```

Run the backend development server:
```bash
uvicorn backend.main:app --reload --host 0.0.0.0 --port 8000
```
The interactive API documentation will be available at `http://localhost:8000/docs`.

### 2. Frontend Setup

In a separate terminal:
```bash
cd frontend

# Install dependencies
npm install

# Start development server
npm start
```
The application will launch at `http://localhost:3000`.

---

## Environment Variables

Configure these settings in your `.env` file (copied from `.env.example`):

| Variable | Description | Default | Required |
| :--- | :--- | :--- | :--- |
| `GEMINI_API_KEY` | Google Gemini API key for synthesis, claim verification, and chat | `""` | **Yes** |
| `GEMINI_MODEL` | Gemini model identifier | `gemini-3.5-flash-lite` | No |
| `S2_API_KEY` | Semantic Scholar API key for elevated search rate limits | `""` | No |
| `CORE_API_KEY` | CORE API key for open academic search | `""` | No |
| `DOC_DEPTH` | Depth for composer generation (`extended` or `brief`) | `extended` | No |
| `VERIFY_MAX_WORKERS` | Max concurrent worker threads for verification checks | `4` | No |
| `INGEST_MAX_PDF_MB` | Maximum allowed file size for PDF paper downloads | `2.0` | No |
| `INGEST_DOWNLOAD_TIMEOUT_S` | Network timeout in seconds for paper downloads | `60` | No |
| `RA_PDF_CACHE_DIR` | Local cache directory for downloaded PDFs | `.cache/pdf` | No |
| `RA_CACHE_DIR` | Local cache directory for LLM response caching | `.cache/llm` | No |
| `SEARCH_CACHE_DIR` | Local cache directory for academic search results | `.cache/search` | No |

---

## Running Tests

### Backend Tests
To install testing dependencies and run the complete test suite:
```bash
# Install test dependencies
pip install -r requirements-dev.txt

# Run all backend tests
python -m pytest

# Run tests with verbose output and coverage
python -m pytest -v
```

### Frontend Tests
Run unit tests for React components and API services:
```bash
cd frontend
npm test -- --watchAll=false
```

To create a production build of the frontend:
```bash
cd frontend
npm run build
```

---

## Team Roles & Responsibilities

| Role | Domain / Responsibilities | Assigned Engineer |
| :--- | :--- | :--- |
| **Person A** | **Academic Search, Document Ingestion & Vector Storage**<br>• Semantic Scholar, arXiv, and CORE search adapters<br>• PyMuPDF parsing, text chunking, and local PDF cache<br>• ChromaDB vector store and SentenceTransformers embeddings |
| **Person B** | **Summarization & Citation Engineering**<br>• Individual per-paper summary and claim extraction<br>• Cross-paper comparative synthesis<br>• IEEE and APA bibliographic formatting and in-text citation markers |
| **Person C** | **Guided Input, Document Composition, Renderers & Frontend**<br>• Three-tier guided input questionnaire for student project details<br>• PPTX, DOCX, and PDF composers with structured layout templates<br>• React SPA implementation, live preview modals, and downloads | 
| **Person D** | **Claim Verification, Orchestrator Architecture & API Layer**<br>• NLI-based claim grounding and contradiction detection with multi-threading<br>• LangGraph pipeline coordination and state machine routing<br>• FastAPI REST endpoints, WebSocket progress streaming, and test harnesses |

---

## Known Limitations

- **Free-Tier API Rate Limits**: When operating on free-tier Gemini API keys or public Semantic Scholar endpoints, concurrent request bursts may encounter transient rate limits. The system implements caching and retry logic to mitigate this.
- **Initial Execution Latency**: First-time execution downloads embedding models (`all-MiniLM-L6-v2`) and parses multiple full-text PDF documents. Subsequent runs on identical queries benefit from cached PDFs and cached search records.
- **Approximate Document Previews**: The in-browser document preview provides an HTML/Markdown approximation of the content. Exact typography, margins, callout boxes, and presentation slide layouts should be reviewed in the exported `.docx`, `.pptx`, or `.pdf` deliverables.
