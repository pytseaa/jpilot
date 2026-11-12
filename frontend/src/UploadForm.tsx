import { type SubmitEvent, useState } from "react";
import { createRequest, type Preferences, type Review } from "./api";
import { NO_EMPLOYMENT_TYPE, PreferenceFields } from "./PreferenceFields";

export function UploadForm({ onRead }: { onRead: (review: Review) => void }) {
  const [file, setFile] = useState<File | null>(null);
  const [targetRole, setTargetRole] = useState("");
  const [prefs, setPrefs] = useState<Preferences>({
    employment_types: [],
    experience_band: null,
    industry: null,
  });
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  const submit = async (event: SubmitEvent) => {
    event.preventDefault();
    if (!file) return;
    if (prefs.employment_types.length === 0) {
      setError(NO_EMPLOYMENT_TYPE);
      return;
    }
    setError("");
    setBusy(true);
    try {
      onRead(await createRequest(file, targetRole, prefs));
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setBusy(false);
    }
  };

  return (
    <form onSubmit={submit}>
      <h1>Find jobs that fit your CV</h1>
      <label>
        CV (text-based PDF)
        <input
          type="file"
          accept="application/pdf"
          required
          onChange={(e) => setFile(e.target.files?.[0] ?? null)}
        />
      </label>
      <label>
        Target role (optional, we suggest one from your CV if you leave it empty)
        <input value={targetRole} onChange={(e) => setTargetRole(e.target.value)} />
      </label>
      <PreferenceFields value={prefs} onChange={setPrefs} />
      {error && <p role="alert" className="error">{error}</p>}
      <button type="submit" disabled={busy}>
        {busy ? "Reading your CV..." : "Read my CV"}
      </button>
    </form>
  );
}
