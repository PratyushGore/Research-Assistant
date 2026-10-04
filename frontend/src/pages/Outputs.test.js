import React from "react";
import { render, screen, fireEvent, waitFor, within } from "@testing-library/react";
import Outputs, { getDeliverableFileType } from "./Outputs";
import * as api from "../api";

const mockNavigate = jest.fn();
let mockLocationState = {};

jest.mock("react-router-dom", () => ({
  useNavigate: () => mockNavigate,
  useLocation: () => ({ state: mockLocationState }),
}));

// Mock docx-preview and pptx-preview
const mockRenderAsync = jest.fn().mockResolvedValue({});
jest.mock("docx-preview", () => ({
  renderAsync: (...args) => mockRenderAsync(...args),
}));

const mockPptxPreview = jest.fn().mockResolvedValue({});
const mockPptxDestroy = jest.fn();
jest.mock("pptx-preview", () => ({
  init: () => ({
    preview: (...args) => mockPptxPreview(...args),
    destroy: () => mockPptxDestroy(),
  }),
}));

describe("Outputs - getDeliverableFileType", () => {
  test("correctly identifies docx", () => {
    expect(
      getDeliverableFileType({ download_url: "/files/paper.docx" }, { id: "research_paper" })
    ).toBe("docx");
  });

  test("correctly identifies pptx from url or id", () => {
    expect(
      getDeliverableFileType({ download_url: "/files/presentation.pptx" }, { id: "ppt" })
    ).toBe("pptx");
    expect(
      getDeliverableFileType({ download_url: "/download/123" }, { id: "ppt" })
    ).toBe("pptx");
  });

  test("correctly identifies pdf", () => {
    expect(
      getDeliverableFileType({ download_url: "/files/document.pdf" }, { id: "research_paper" })
    ).toBe("pdf");
  });
});

describe("Outputs Component - Preview and Download Actions", () => {
  const sampleResults = [
    {
      output_type: "research_paper",
      download_url: "/download/test-paper.docx",
    },
    {
      output_type: "ppt",
      download_url: "/download/test-slides.pptx",
    },
  ];

  beforeEach(() => {
    jest.clearAllMocks();
    mockLocationState = {
      session_id: "sess-abc-123",
      topic: "Deep Learning for Robotics",
      results: sampleResults,
      selectedOutputs: ["research_paper", "ppt"],
    };
  });

  test("Download buttons still have download attribute pointing to download URL", () => {
    render(<Outputs />);

    const downloadLinks = screen.getAllByRole("link", { name: /download/i });
    expect(downloadLinks.length).toBeGreaterThanOrEqual(2);

    const hrefs = downloadLinks.map((link) => link.getAttribute("href"));
    expect(hrefs.some((h) => h.includes("/download/test-paper.docx"))).toBe(true);
    expect(hrefs.some((h) => h.includes("/download/test-slides.pptx"))).toBe(true);

    downloadLinks.forEach((link) => {
      expect(link).toHaveAttribute("download");
    });
  });

  test("Preview button opens modal, fetches file, and invokes docx-preview", async () => {
    const dummyBlob = new Blob(["fake docx content"], { type: "application/vnd.openxmlformats-officedocument.wordprocessingml.document" });
    const dummyBuffer = new ArrayBuffer(16);
    jest.spyOn(api, "fetchDeliverableFile").mockResolvedValue({
      blob: dummyBlob,
      arrayBuffer: dummyBuffer,
    });

    render(<Outputs />);

    // Find and click the Preview button for Research Paper
    const previewBtn = screen.getByRole("button", { name: /preview research paper/i });
    expect(previewBtn).toBeInTheDocument();

    fireEvent.click(previewBtn);

    // Modal dialog is displayed
    const modal = await screen.findByRole("dialog");
    expect(modal).toBeInTheDocument();
    expect(screen.getByText("DOCX PREVIEW")).toBeInTheDocument();
    expect(within(modal).getByRole("heading", { name: "Research Paper" })).toBeInTheDocument();

    // Verify fetchDeliverableFile was called
    expect(api.fetchDeliverableFile).toHaveBeenCalledWith(
      expect.stringContaining("/download/test-paper.docx")
    );

    // Verify docx renderAsync called
    await waitFor(() => {
      expect(mockRenderAsync).toHaveBeenCalled();
    });

    // Close preview via close button
    const closeBtn = screen.getByRole("button", { name: /close preview/i });
    fireEvent.click(closeBtn);

    await waitFor(() => {
      expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    });
  });

  test("Preview modal can be closed via Escape key", async () => {
    const dummyBlob = new Blob(["fake docx"], { type: "application/docx" });
    jest.spyOn(api, "fetchDeliverableFile").mockResolvedValue({
      blob: dummyBlob,
      arrayBuffer: new ArrayBuffer(8),
    });

    render(<Outputs />);

    const previewBtn = screen.getByRole("button", { name: /preview research paper/i });
    fireEvent.click(previewBtn);

    await screen.findByRole("dialog");

    // Press Escape
    fireEvent.keyDown(window, { key: "Escape", code: "Escape" });

    await waitFor(() => {
      expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    });
  });

  test("Preview handles fetch/render failure with clear message and Download instead option", async () => {
    jest.spyOn(api, "fetchDeliverableFile").mockRejectedValue(
      new Error("Network connection error")
    );

    render(<Outputs />);

    const previewBtn = screen.getByRole("button", { name: /preview research paper/i });
    fireEvent.click(previewBtn);

    await screen.findByRole("dialog");

    await waitFor(() => {
      expect(screen.getByText(/unable to render in-browser preview/i)).toBeInTheDocument();
      expect(screen.getByText(/Network connection error/i)).toBeInTheDocument();
    });

    const fallbackDownload = screen.getByRole("link", { name: /download instead/i });
    expect(fallbackDownload).toBeInTheDocument();
    expect(fallbackDownload).toHaveAttribute("download");
  });
});
