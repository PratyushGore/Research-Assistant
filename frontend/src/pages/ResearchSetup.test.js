import React from "react";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import ResearchSetup from "./ResearchSetup";
import * as api from "../api";

const mockNavigate = jest.fn();

jest.mock("react-router-dom", () => ({
  useNavigate: () => mockNavigate,
}));

describe("ResearchSetup Component - Paper Count Stepper", () => {
  beforeEach(() => {
    jest.restoreAllMocks();
    sessionStorage.clear();
    api.setLastMaxPapers(8);
  });

  test("renders with default paper count of 8 and helper text", () => {
    render(<ResearchSetup />);

    const input = screen.getByLabelText(/number of research papers/i);
    expect(input).toBeInTheDocument();
    expect(input).toHaveValue(8);

    expect(
      screen.getByText("More papers take longer to analyse")
    ).toBeInTheDocument();
  });

  test("stepper limits: decrement stops at 3 and button becomes disabled", () => {
    render(<ResearchSetup />);

    const decBtn = screen.getByRole("button", { name: /decrease papers/i });
    const input = screen.getByLabelText(/number of research papers/i);

    // Initial is 8; decrement 5 times to reach min of 3
    for (let i = 0; i < 5; i++) {
      fireEvent.click(decBtn);
    }
    expect(input).toHaveValue(3);
    expect(decBtn).toBeDisabled();

    // Extra click should not go below 3
    fireEvent.click(decBtn);
    expect(input).toHaveValue(3);
  });

  test("stepper limits: increment stops at 15 and button becomes disabled", () => {
    render(<ResearchSetup />);

    const incBtn = screen.getByRole("button", { name: /increase papers/i });
    const input = screen.getByLabelText(/number of research papers/i);

    // Initial is 8; increment 7 times to reach max of 15
    for (let i = 0; i < 7; i++) {
      fireEvent.click(incBtn);
    }
    expect(input).toHaveValue(15);
    expect(incBtn).toBeDisabled();

    // Extra click should not go above 15
    fireEvent.click(incBtn);
    expect(input).toHaveValue(15);
  });

  test("typed input: typing out-of-bounds clamps to limits (min 3, max 15)", () => {
    render(<ResearchSetup />);

    const input = screen.getByLabelText(/number of research papers/i);

    // Typing > 15 clamps immediately
    fireEvent.change(input, { target: { value: "20" } });
    expect(input).toHaveValue(15);

    // Typing < 3 clamps on blur
    fireEvent.change(input, { target: { value: "1" } });
    fireEvent.blur(input);
    expect(input).toHaveValue(3);
  });

  test("submitting calls startResearch with topic and max_papers", async () => {
    jest.spyOn(api, "startResearch").mockResolvedValue({ session_id: "sess-999" });

    render(<ResearchSetup />);

    const topicInput = screen.getByLabelText(/research topic/i);
    const incBtn = screen.getByRole("button", { name: /increase papers/i });
    const continueBtn = screen.getByRole("button", { name: /continue/i });

    // Enter topic
    fireEvent.change(topicInput, { target: { value: "AI in Healthcare" } });

    // Change papers to 10 (+2 clicks)
    fireEvent.click(incBtn);
    fireEvent.click(incBtn);

    // Click continue
    fireEvent.click(continueBtn);

    await waitFor(() => {
      expect(api.startResearch).toHaveBeenCalledWith("AI in Healthcare", 10);
      expect(mockNavigate).toHaveBeenCalledWith("/research-progress", {
        state: {
          session_id: "sess-999",
          topic: "AI in Healthcare",
          max_papers: 10,
          phase: "research",
        },
      });
    });
  });

  test("persists paper choice in sessionStorage and restores when mounting again", () => {
    const { unmount } = render(<ResearchSetup />);

    const incBtn = screen.getByRole("button", { name: /increase papers/i });
    // Increase to 12 (+4 clicks)
    for (let i = 0; i < 4; i++) {
      fireEvent.click(incBtn);
    }

    const input = screen.getByLabelText(/number of research papers/i);
    expect(input).toHaveValue(12);

    // Unmount (simulating navigation to progress/results)
    unmount();

    // Remount (simulating navigating "Back to Setup")
    render(<ResearchSetup />);
    const newInput = screen.getByLabelText(/number of research papers/i);
    expect(newInput).toHaveValue(12);
  });
});

describe("api.js startResearch - max_papers payload and retry persistence", () => {
  beforeEach(() => {
    jest.restoreAllMocks();
    sessionStorage.clear();
    api.setLastMaxPapers(8);
  });

  test("sends max_papers in POST body to /research", async () => {
    const mockFetch = jest.fn().mockResolvedValue({
      ok: true,
      json: async () => ({ session_id: "sess-abc" }),
    });
    global.fetch = mockFetch;

    await api.startResearch("Autonomous Agents", 12);

    expect(mockFetch).toHaveBeenCalledTimes(1);
    const [url, options] = mockFetch.mock.calls[0];
    expect(url).toBe("http://localhost:8000/research");
    expect(options.method).toBe("POST");
    const body = JSON.parse(options.body);
    expect(body).toEqual({
      topic: "Autonomous Agents",
      max_papers: 12,
    });
  });

  test("retrying startResearch without max_papers argument reuses stored count", async () => {
    const mockFetch = jest.fn().mockResolvedValue({
      ok: true,
      json: async () => ({ session_id: "sess-retry" }),
    });
    global.fetch = mockFetch;

    // First call sets 14
    await api.startResearch("Autonomous Agents", 14);

    // Second call (like retry pipeline in ResearchProgress.js: startResearch(topic))
    await api.startResearch("Autonomous Agents");

    const [, secondCallOptions] = mockFetch.mock.calls[1];
    const secondBody = JSON.parse(secondCallOptions.body);
    expect(secondBody).toEqual({
      topic: "Autonomous Agents",
      max_papers: 14,
    });
  });
});
