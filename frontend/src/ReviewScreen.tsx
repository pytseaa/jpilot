import { useState } from "react";
import { keepReviewed, type Review, type Reviewed } from "./api";
import { BandAndIndustry, EmploymentPills, NO_EMPLOYMENT_TYPE } from "./PreferenceFields";

type Props = { review: Review; fileName: string | null; onRestart: () => void };

// Not a <form>: pressing Enter in a field must never act as the Search button.
export function ReviewScreen({ review, fileName, onRestart }: Props) {
  const { id, ...initial } = review;
  const [values, setValues] = useState<Reviewed>(initial);
  const [newKeyword, setNewKeyword] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [kept, setKept] = useState(false);

  const update = (patch: Partial<Reviewed>) => {
    setValues({ ...values, ...patch });
    setKept(false);
  };

  const addKeyword = () => {
    const keyword = newKeyword.trim();
    const known = values.keywords.some((k) => k.toLowerCase() === keyword.toLowerCase());
    if (keyword && !known) update({ keywords: [...values.keywords, keyword] });
    setNewKeyword("");
  };

  const search = async () => {
    if (values.employment_types.length === 0) {
      setError(NO_EMPLOYMENT_TYPE);
      return;
    }
    setError("");
    setBusy(true);
    try {
      await keepReviewed(id, values);
      setKept(true);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setBusy(false);
    }
  };

  return (
    <section>
      <h1>Check what we understood</h1>
      <div className="review-meta">
        {fileName && <span className="file-chip">{fileName}</span>}
        <span className="note">Region: Hong Kong</span>
      </div>
      <p className="note">Everything here is optional to change. Nothing is searched until you press Search.</p>
      <div className="review-card">
        <label>
          CV summary
          <textarea
            rows={6}
            value={values.summary}
            onChange={(e) => update({ summary: e.target.value })}
          />
        </label>
        <label>
          Target role
          <input value={values.target_role} onChange={(e) => update({ target_role: e.target.value })} />
        </label>
        <div className="field">
          <span id="keywords-label">Keywords</span>
          <ul className="chips" aria-labelledby="keywords-label">
            {values.keywords.map((keyword) => (
              <li key={keyword}>
                {keyword}
                <button
                  type="button"
                  aria-label={`Remove ${keyword}`}
                  onClick={() => update({ keywords: values.keywords.filter((k) => k !== keyword) })}
                >
                  &times;
                </button>
              </li>
            ))}
          </ul>
          <div className="add-keyword">
            <input
              aria-label="Add a keyword"
              value={newKeyword}
              onChange={(e) => setNewKeyword(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter") addKeyword();
              }}
            />
            <button type="button" onClick={addKeyword}>
              Add
            </button>
          </div>
        </div>
        <div className="composer-row">
          <EmploymentPills value={values} onChange={update} />
        </div>
        <div className="composer-row">
          <BandAndIndustry value={values} onChange={update} />
          <button type="button" className="search" onClick={search} disabled={busy}>
            Search
          </button>
        </div>
      </div>
      {error && <p role="alert" className="error">{error}</p>}
      {kept && (
        <p role="status" className="note">
          Your reviewed values are kept. Searching comes in a later step.
        </p>
      )}
      <div className="actions">
        <button type="button" className="secondary" onClick={onRestart}>
          Upload a different CV
        </button>
      </div>
    </section>
  );
}
