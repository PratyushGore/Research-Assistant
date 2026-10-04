# Multi-Agent Research Assistant - Frontend

React single-page application (SPA) providing an interactive user interface for the Multi-Agent AI Research & Publication Assistant.

## Overview

The frontend guides students and researchers through a 3-step research and publishing workflow:
1. **Research Setup (`ResearchSetup.js`)**: Configure research topic and select target paper count (3 to 15 papers).
2. **Research Monitoring & Q&A (`ResearchResults.js`)**: Real-time progress monitoring via WebSockets, interactive paper list with external links, collapsible summaries and claim verifications, and an always-on grounded research Q&A assistant.
3. **Guided Intake & Outputs (`Outputs.js`)**: Three-tier questionnaire (cover details, presentation specs, academic methodology), deliverable selection (PPT, Research Paper, Literature Survey, Executive Summary), live document preview modal, and direct downloads.

## Tech Stack

- **Framework**: React 18 (Create React App)
- **Styling**: Vanilla CSS with responsive design system and glassmorphism styling
- **API & Streaming**: Native Fetch API and WebSocket client (`src/api.js`)
- **Testing**: Jest and React Testing Library

## Getting Started

### Installation
```bash
npm install
```

### Running Locally
```bash
npm start
```
Runs the development server at [http://localhost:3000](http://localhost:3000). The frontend proxies requests or connects directly to the FastAPI backend running at `http://localhost:8000`.

### Running Tests
```bash
npm test -- --watchAll=false
```

### Production Build
```bash
npm run build
```
Generates production-ready bundled and minified static assets in the `build/` directory.
