import { act, cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import { ApiError, getResults, getStage, startSearch, type Review, type Results } from "./api";
import { ReviewScreen } from "./ReviewScreen";

vi.mock("./api", async (importOriginal) => {
  const actual = await importOriginal<typeof import("./api")>();
  return { ...actual, getResults: vi.fn(), getStage: vi.fn(), startSearch: vi.fn() };
});

const review: Review = {
  id: "request-1", summary: "PRIVATE CV SUMMARY", keywords: ["SQL"], target_role: "Analyst",
  employment_types: ["full-time"], experience_band: null, industry: null,
};
const results: Results = { jobs: [], dropped_claims: 0, skipped_jobs: 1, explanation: "No jobs could be checked." };

beforeEach(() => {
  vi.useFakeTimers();
  vi.mocked(startSearch).mockResolvedValue(review);
});
afterEach(() => {
  cleanup();
  vi.useRealTimers();
  vi.resetAllMocks();
});

async function begin() {
  const onFinished = vi.fn();
  render(<ReviewScreen review={review} fileName="private.pdf" onRestart={vi.fn()} onFinished={onFinished} />);
  await act(async () => { fireEvent.click(screen.getByRole("button", { name: "Search" })); });
  return onFinished;
}
async function poll() {
  await act(async () => { await vi.advanceTimersByTimeAsync(2000); });
}

it("clears the review immediately at completion and retries loading results without searching again", async () => {
  vi.mocked(getStage).mockResolvedValue({ stage: "done" });
  vi.mocked(getResults).mockRejectedValueOnce(new Error("Results could not be loaded."))
    .mockResolvedValueOnce(results);
  const onFinished = await begin();
  await poll();
  expect(onFinished).toHaveBeenCalledWith(review.id);
  expect(screen.queryByLabelText("CV summary")).toBeNull();
  expect(screen.queryByText("private.pdf")).toBeNull();
  expect(screen.queryByRole("button", { name: "Search" })).toBeNull();
  expect(screen.getByRole("alert").textContent).toContain("could not be loaded");
  await poll();
  expect(getStage).toHaveBeenCalledTimes(1);
  await act(async () => { fireEvent.click(screen.getByRole("button", { name: "Load results again" })); });
  expect(screen.getByText(results.explanation!)).toBeTruthy();
  expect(screen.getByText(/1 job was skipped/)).toBeTruthy();
  expect(screen.queryByText(/No suitable jobs/)).toBeNull();
  expect(getResults).toHaveBeenCalledTimes(2);
  expect(startSearch).toHaveBeenCalledTimes(1);
});

it("stops polling and clears review data when the backend loses the request", async () => {
  vi.mocked(getStage).mockRejectedValue(new ApiError("Request missing", 404));
  const onFinished = await begin();
  await poll();
  expect(onFinished).toHaveBeenCalledWith(review.id);
  expect(screen.queryByLabelText("CV summary")).toBeNull();
  expect(screen.getByRole("alert").textContent).toContain("upload your CV again");
  await poll();
  expect(getStage).toHaveBeenCalledTimes(1);
  expect(getResults).not.toHaveBeenCalled();
});

it("shows a terminal backend failure without requesting a partial list", async () => {
  vi.mocked(getStage).mockResolvedValue({ stage: "failed", error: "Restart Qwen and upload again." });
  const onFinished = await begin();
  await poll();
  expect(screen.getByRole("alert").textContent).toBe("Restart Qwen and upload again.");
  expect(onFinished).toHaveBeenCalledWith(review.id);
  expect(screen.queryByLabelText("CV summary")).toBeNull();
  expect(getResults).not.toHaveBeenCalled();
});

it("clears review data when the worker cannot start", async () => {
  vi.mocked(startSearch).mockRejectedValue(new ApiError("Search failed. Upload again.", 503));
  const onFinished = await begin();
  expect(onFinished).toHaveBeenCalledWith(review.id);
  expect(screen.queryByLabelText("CV summary")).toBeNull();
  expect(screen.getByRole("alert").textContent).toContain("Upload again");
  await poll();
  expect(getStage).not.toHaveBeenCalled();
});

it("recovers from a temporary status connection failure", async () => {
  vi.mocked(getStage).mockRejectedValueOnce(new Error("Connection interrupted"))
    .mockResolvedValueOnce({ stage: "done" });
  vi.mocked(getResults).mockResolvedValue(results);
  const onFinished = await begin();
  await poll();
  expect(onFinished).not.toHaveBeenCalled();
  expect(screen.getByLabelText("CV summary")).toBeTruthy();
  await poll();
  expect(onFinished).toHaveBeenCalledWith(review.id);
  expect(screen.getByText(results.explanation!)).toBeTruthy();
});

it("handles a backend restart between completion and fetching results", async () => {
  vi.mocked(getStage).mockResolvedValue({ stage: "done" });
  vi.mocked(getResults).mockRejectedValue(new ApiError("Request missing", 404));
  await begin();
  await poll();
  expect(screen.getByRole("alert").textContent).toContain("results are no longer available");
  expect(screen.queryByRole("button", { name: "Load results again" })).toBeNull();
  expect(screen.queryByLabelText("CV summary")).toBeNull();
});

it("recovers a search whose start response was lost", async () => {
  vi.mocked(startSearch).mockRejectedValue(new Error("Connection interrupted"));
  vi.mocked(getStage).mockResolvedValue({ stage: "done" });
  vi.mocked(getResults).mockResolvedValue(results);
  const onFinished = await begin();
  await poll();
  expect(onFinished).toHaveBeenCalledWith(review.id);
  expect(screen.queryByLabelText("CV summary")).toBeNull();
  expect(screen.getByText(results.explanation!)).toBeTruthy();
  expect(startSearch).toHaveBeenCalledTimes(1);
});

it("allows a retry when a lost start response was never accepted by the backend", async () => {
  vi.mocked(startSearch).mockRejectedValue(new Error("Connection interrupted"));
  vi.mocked(getStage).mockResolvedValue({ stage: null });
  const onFinished = await begin();
  await poll();
  expect(onFinished).not.toHaveBeenCalled();
  expect(screen.getByRole("alert").textContent).toContain("has not started");
  expect((screen.getByRole("button", { name: "Search" }) as HTMLButtonElement).disabled).toBe(false);
  await poll();
  expect(getStage).toHaveBeenCalledTimes(1);
});
