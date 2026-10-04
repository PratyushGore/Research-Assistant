import React from "react";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import ResearchResults, { getPaperUrl } from "./ResearchResults";
import * as api from "../api";

// Mock router hooks
const mockNavigate = jest.fn();
let mockLocationState = {};

jest.mock("react-router-dom", () => ({
  useNavigate: () => mockNavigate,
  useLocation: () => ({ state: mockLocationState }),
}));

describe("ResearchResults - getPaperUrl helper rules", () => {
  test("accepts valid https URL", () => {
    const paper = { url: "https://example.com/paper.pdf", paper_id: "p1" };
    expect(getPaperUrl(paper)).toBe("https://example.com/paper.pdf");
  });

  test("accepts valid http URL", () => {
    const paper = { url: "http://arxiv.org/abs/2301.12345", paper_id: "p2" };
    expect(getPaperUrl(paper)).toBe("http://arxiv.org/abs/2301.12345");
  });

  test("falls back to arXiv URL when url is empty and paper_id starts with arxiv:", () => {
    const paper = { url: "", paper_id: "arxiv:2401.99999" };
    expect(getPaperUrl(paper)).toBe("https://arxiv.org/abs/2401.99999");
  });

  test("falls back to arXiv URL with case-insensitivity and trim", () => {
    const paper = { url: "   ", paper_id: "arXiv: 2106.09685" };
    expect(getPaperUrl(paper)).toBe("https://arxiv.org/abs/2106.09685");
  });

  test("rejects javascript: URLs", () => {
    const paper = { url: "javascript:alert(document.domain)", paper_id: "p_bad" };
    expect(getPaperUrl(paper)).toBeNull();
  });

  test("rejects data: and file: URLs", () => {
    expect(getPaperUrl({ url: "data:text/html,test", paper_id: "p3" })).toBeNull();
    expect(getPaperUrl({ url: "file:///etc/passwd", paper_id: "p4" })).toBeNull();
  });

  test("returns null if no URL and non-arxiv paper_id", () => {
    expect(getPaperUrl({ url: "", paper_id: "pubmed:12345" })).toBeNull();
    expect(getPaperUrl({ url: null, paper_id: "custom_paper_1" })).toBeNull();
    expect(getPaperUrl(null)).toBeNull();
  });
});

describe("ResearchResults Component - Links and Collapsible Section", () => {
  beforeEach(() => {
    jest.clearAllMocks();
    mockLocationState = { session_id: "test-session-123" };
  });

  test("renders View paper button only when url is valid or arxiv fallback exists", async () => {
    const mockFindings = {
      topic: "Quantum Error Correction",
      summaries: [
        {
          paper_id: "arxiv:2303.00001",
          title: "Surface Code Architectures",
          summary: "Summary of surface codes.",
          url: "",
        },
        {
          paper_id: "paper_with_web_url",
          title: "Cat Qubits Synthesis",
          summary: "Summary of cat qubits.",
          url: "https://nature.com/articles/s41586-023",
        },
        {
          paper_id: "paper_with_xss",
          title: "Malicious Paper",
          summary: "Summary with bad url.",
          url: "javascript:alert(1)",
        },
        {
          paper_id: "internal_paper_no_link",
          title: "Internal Proprietary Notes",
          summary: "No external url available.",
          url: "",
        },
      ],
      claims: [],
      contradictions: [],
    };

    jest.spyOn(api, "getResearchResults").mockResolvedValue(mockFindings);

    render(<ResearchResults />);

    await waitFor(() => {
      expect(screen.getByText("Surface Code Architectures")).toBeInTheDocument();
    });

    const links = screen.getAllByRole("link", { name: /view paper/i });
    expect(links).toHaveLength(2);

    expect(links[0]).toHaveAttribute("href", "https://arxiv.org/abs/2303.00001");
    expect(links[0]).toHaveAttribute("target", "_blank");
    expect(links[0]).toHaveAttribute("rel", "noopener noreferrer");

    expect(links[1]).toHaveAttribute("href", "https://nature.com/articles/s41586-023");
    expect(links[1]).toHaveAttribute("target", "_blank");
  });

  test("collapse toggle hides/shows the list while keeping header and badge visible", async () => {
    const mockFindings = {
      topic: "Deep Reinforcement Learning",
      summaries: [
        {
          paper_id: "arxiv:2005.00001",
          title: "PPO Policy Optimization",
          summary: "Proximal policy optimization summary.",
          url: "https://arxiv.org/abs/2005.00001",
        },
      ],
      claims: [],
      contradictions: [],
    };

    jest.spyOn(api, "getResearchResults").mockResolvedValue(mockFindings);

    render(<ResearchResults />);

    await waitFor(() => {
      expect(screen.getByText("PPO Policy Optimization")).toBeInTheDocument();
    });

    // Badge is visible
    expect(screen.getByText(/1 Source Analyzed/i)).toBeInTheDocument();

    const toggleBtn = screen.getByRole("button", { name: /collapse per-paper summaries/i });
    expect(toggleBtn).toHaveAttribute("aria-expanded", "true");
    expect(toggleBtn).toHaveTextContent(/collapse/i);

    const collapsibleWrapper = document.getElementById("paper-summaries-collapsible");
    expect(collapsibleWrapper).toHaveClass("is-expanded");
    expect(collapsibleWrapper).not.toHaveClass("is-collapsed");

    // Click to collapse
    fireEvent.click(toggleBtn);

    expect(toggleBtn).toHaveAttribute("aria-expanded", "false");
    expect(toggleBtn).toHaveTextContent(/expand/i);
    expect(collapsibleWrapper).toHaveClass("is-collapsed");

    // Header and badge still visible when collapsed
    expect(screen.getByText("Per-Paper Summaries")).toBeInTheDocument();
    expect(screen.getByText(/1 Source Analyzed/i)).toBeInTheDocument();

    // Click again to expand
    fireEvent.click(toggleBtn);
    expect(toggleBtn).toHaveAttribute("aria-expanded", "true");
    expect(toggleBtn).toHaveTextContent(/collapse/i);
    expect(collapsibleWrapper).toHaveClass("is-expanded");
  });

  test("renders notice banner when paper_notice is present", async () => {
    const noticeText = "You asked for 15 papers but only 9 were available for this topic.";
    const mockFindings = {
      topic: "Deterministic Search Pipeline",
      requested_papers: 15,
      available_papers: 9,
      paper_notice: noticeText,
      summaries: [
        {
          paper_id: "arxiv:2401.00001",
          title: "Deterministic Search Algorithms",
          summary: "A study on determinism.",
          url: "https://arxiv.org/abs/2401.00001",
        },
      ],
      claims: [],
      contradictions: [],
    };

    jest.spyOn(api, "getResearchResults").mockResolvedValue(mockFindings);

    render(<ResearchResults />);

    await waitFor(() => {
      expect(screen.getByText("Deterministic Search Algorithms")).toBeInTheDocument();
    });

    // Notice banner should be visible with notice text
    const banner = screen.getByTestId("paper-notice-banner");
    expect(banner).toBeInTheDocument();
    expect(banner).toHaveTextContent(noticeText);

    // Chip should be visible with requested and analysed numbers
    const chip = screen.getByTestId("paper-count-chip");
    expect(chip).toBeInTheDocument();
    expect(chip).toHaveTextContent("Requested 15 - Analysed 9");
  });

  test("does not render notice banner when paper_notice is absent", async () => {
    const mockFindings = {
      topic: "Full Availability Topic",
      requested_papers: 8,
      available_papers: 8,
      paper_notice: null,
      summaries: [
        {
          paper_id: "arxiv:2401.00002",
          title: "Full Set Paper",
          summary: "All papers available.",
          url: "https://arxiv.org/abs/2401.00002",
        },
      ],
      claims: [],
      contradictions: [],
    };

    jest.spyOn(api, "getResearchResults").mockResolvedValue(mockFindings);

    render(<ResearchResults />);

    await waitFor(() => {
      expect(screen.getByText("Full Set Paper")).toBeInTheDocument();
    });

    // Banner must NOT be rendered
    expect(screen.queryByTestId("paper-notice-banner")).toBeNull();
    expect(screen.queryByText(/You asked for/i)).toBeNull();

    // Chip should still be rendered when both numbers exist
    const chip = screen.getByTestId("paper-count-chip");
    expect(chip).toBeInTheDocument();
    expect(chip).toHaveTextContent("Requested 8 - Analysed 8");
  });
});

