export type Preferences = {
  employment_types: string[];
  experience_band: string | null;
  industry: string | null;
};
export type Reviewed = Preferences & { summary: string; keywords: string[]; target_role: string };
export type Review = Reviewed & { id: string };
// null until Search is pressed.
export type Stage = "searching" | "done" | "failed" | null;
export type ResultJob = {
  job_id: string;
  title: string | null;
  employer: string | null;
  location: string | null;
  apply_link: string | null;
  unverified: boolean;
};

async function call<T>(url: string, init: RequestInit = {}): Promise<T> {
  let res: Response;
  try {
    res = await fetch(url, init);
  } catch {
    throw new Error("Could not reach the backend. Is it running?");
  }
  if (res.ok) return res.json();
  const body = await res.json().catch(() => null);
  // The backend sends a sentence for its own errors, and a list for a bad form value.
  throw new Error(typeof body?.detail === "string" ? body.detail : "Please check the form and try again.");
}

export function createRequest(cv: File, targetRole: string, prefs: Preferences): Promise<Review> {
  const form = new FormData();
  form.append("cv", cv);
  form.append("target_role", targetRole);
  prefs.employment_types.forEach((type) => form.append("employment_types", type));
  form.append("experience_band", prefs.experience_band ?? "");
  form.append("industry", prefs.industry ?? "");
  return call("/api/search-requests", { method: "POST", body: form });
}

/** Keeps the reviewed values on the backend and starts the search in the background. */
export function startSearch(id: string, reviewed: Reviewed): Promise<Review> {
  return call(`/api/search-requests/${id}/search`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(reviewed),
  });
}

export function getStage(id: string): Promise<{ stage: Stage }> {
  return call(`/api/search-requests/${id}/status`);
}

export function getJobs(id: string): Promise<{ jobs: ResultJob[] }> {
  return call(`/api/search-requests/${id}/results`);
}
