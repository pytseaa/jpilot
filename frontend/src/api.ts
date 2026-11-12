export type Preferences = {
  employment_types: string[];
  experience_band: string | null;
  industry: string | null;
};
export type Reviewed = Preferences & { summary: string; keywords: string[]; target_role: string };
export type Review = Reviewed & { id: string };

async function call(url: string, init: RequestInit): Promise<Review> {
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

/** Keeps the reviewed values on the backend. Nothing is searched yet. */
export function keepReviewed(id: string, reviewed: Reviewed): Promise<Review> {
  return call(`/api/search-requests/${id}/search`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(reviewed),
  });
}
