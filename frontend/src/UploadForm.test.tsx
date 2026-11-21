import { act, cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";
import { ApiError, createRequest, type Review } from "./api";
import { UploadForm } from "./UploadForm";

vi.mock("./api", async (importOriginal) => {
  const actual = await importOriginal<typeof import("./api")>();
  return { ...actual, createRequest: vi.fn() };
});

afterEach(() => { cleanup(); vi.resetAllMocks(); });

const message = "We could not read any text from this file. Please upload a text-based PDF, not a scan or an image.";
const cv = new File(["synthetic PDF"], "synthetic.pdf", { type: "application/pdf" });

async function rejectUpload() {
  vi.mocked(createRequest).mockRejectedValueOnce(new ApiError(message, 422));
  const onRead = vi.fn();
  const { container } = render(<UploadForm onRead={onRead} />);
  const input = container.querySelector<HTMLInputElement>('input[type="file"]')!;
  fireEvent.click(screen.getByRole("button", { name: "full-time" }));
  fireEvent.change(input, { target: { files: [cv] } });
  await act(async () => { fireEvent.click(screen.getByRole("button", { name: "Read my CV" })); });
  return { input, onRead };
}

it("keeps the unreadable-PDF error visible after clearing the attachment", async () => {
  const { input, onRead } = await rejectUpload();
  expect(screen.getByRole("alert").textContent).toBe(message);
  expect(screen.queryByText(cv.name)).toBeNull();
  expect(input.value).toBe("");
  expect(onRead).not.toHaveBeenCalled();
  await act(async () => { fireEvent.click(screen.getByRole("button", { name: "Read my CV" })); });
  expect(createRequest).toHaveBeenCalledTimes(1);
  expect(screen.getByRole("alert").textContent).toContain("Attach your CV");
});

it("clears the old error when a PDF is selected again and allows a fresh upload", async () => {
  const { input, onRead } = await rejectUpload();
  const review: Review = { id: "fresh", summary: "Synthetic SQL CV", keywords: ["SQL"],
    target_role: "Analyst", employment_types: ["full-time"], experience_band: null, industry: null };
  vi.mocked(createRequest).mockResolvedValueOnce(review);
  fireEvent.change(input, { target: { files: [cv] } });
  expect(screen.queryByRole("alert")).toBeNull();
  await act(async () => { fireEvent.click(screen.getByRole("button", { name: "Read my CV" })); });
  expect(onRead).toHaveBeenCalledWith(review, cv.name);
  expect(createRequest).toHaveBeenCalledTimes(2);
  expect(screen.queryByText(cv.name)).toBeNull();
});
