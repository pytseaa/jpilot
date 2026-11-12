import { type SubmitEvent, useRef, useState } from "react";
import { createRequest, type Preferences, type Review } from "./api";
import {
  EMPLOYMENT_TYPES,
  EXPERIENCE_BANDS,
  INDUSTRIES,
  NO_EMPLOYMENT_TYPE,
  toggleEmploymentType,
} from "./PreferenceFields";

// Static text. A click only fills the target role; nothing is sent to the backend.
const EXAMPLE_ROLES = [
  { role: "Data analyst", about: "SQL, dashboards and reporting" },
  { role: "Accountant", about: "Audit, tax and financial reporting" },
  { role: "Software developer", about: "Backend, frontend and full-stack work" },
];

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
  const fileInput = useRef<HTMLInputElement>(null);

  // A new file makes the last error (which was about the old file) stale.
  const chooseFile = (chosen: File | null) => {
    setFile(chosen);
    setError("");
  };

  const removeFile = () => {
    chooseFile(null);
    // Clear the input too, or picking the same file again would not fire a change.
    if (fileInput.current) fileInput.current.value = "";
  };

  const submit = async (event: SubmitEvent) => {
    event.preventDefault();
    if (!file) {
      setError("Attach your CV as a PDF first.");
      return;
    }
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
    <form className="landing-form" onSubmit={submit}>
      <h1>Find jobs that fit your CV</h1>
      <div className="composer">
        <input
          className="role-input"
          aria-label="Target role (optional)"
          placeholder="Target role (optional, we suggest one from your CV)"
          value={targetRole}
          onChange={(e) => setTargetRole(e.target.value)}
        />
        <div className="composer-row">
          <input
            ref={fileInput}
            type="file"
            accept="application/pdf"
            hidden
            onChange={(e) => chooseFile(e.target.files?.[0] ?? null)}
          />
          <button
            type="button"
            className="attach"
            aria-label="Attach your CV (text-based PDF)"
            onClick={() => fileInput.current?.click()}
          >
            <svg viewBox="0 0 24 24" width="20" height="20" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" aria-hidden="true">
              <path d="M21 11l-8.5 8.5a5 5 0 0 1-7-7L14 4a3.5 3.5 0 0 1 5 5l-8.5 8.5a2 2 0 0 1-3-3L15 7" />
            </svg>
          </button>
          {file && (
            <span className="file-chip">
              {file.name}
              <button type="button" aria-label="Remove the attached CV" onClick={removeFile}>
                &times;
              </button>
            </span>
          )}
          <span className="pills" role="group" aria-label="Employment type (pick one or more)">
            {EMPLOYMENT_TYPES.map((type) => (
              <button
                key={type}
                type="button"
                className="pill"
                aria-pressed={prefs.employment_types.includes(type)}
                onClick={() => setPrefs(toggleEmploymentType(prefs, type))}
              >
                {type}
              </button>
            ))}
          </span>
        </div>
        <div className="composer-row">
          <select
            aria-label="Experience band (optional)"
            value={prefs.experience_band ?? ""}
            onChange={(e) => setPrefs({ ...prefs, experience_band: e.target.value || null })}
          >
            <option value="">Experience band</option>
            {EXPERIENCE_BANDS.map((band) => (
              <option key={band} value={band}>
                {band} years
              </option>
            ))}
          </select>
          <select
            aria-label="Industry (optional)"
            value={prefs.industry ?? ""}
            onChange={(e) => setPrefs({ ...prefs, industry: e.target.value || null })}
          >
            <option value="">Industry</option>
            {INDUSTRIES.map((industry) => (
              <option key={industry} value={industry}>
                {industry}
              </option>
            ))}
          </select>
          <button type="submit" className="send" aria-label="Read my CV" disabled={busy}>
            &uarr;
          </button>
        </div>
      </div>
      <p className="note">Region: Hong Kong</p>
      {error && <p role="alert" className="error">{error}</p>}
      {busy && <p role="status" className="note">Reading your CV...</p>}
      <div className="role-cards">
        {EXAMPLE_ROLES.map(({ role, about }) => (
          <button key={role} type="button" className="role-card" onClick={() => setTargetRole(role)}>
            <strong>{role}</strong>
            {about}
          </button>
        ))}
      </div>
    </form>
  );
}
