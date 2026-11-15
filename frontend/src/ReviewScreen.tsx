import { useEffect, useState } from "react";
import { getResults, getStage, type Results, type Review, type Reviewed, startSearch, type Stage } from "./api";
import { JobList } from "./JobList";
import { BandAndIndustry, EmploymentPills, NO_EMPLOYMENT_TYPE } from "./PreferenceFields";

type Props = { review: Review; fileName: string | null; onRestart: () => void };

const POLL_MS = 2000;

// Not a <form>: pressing Enter in a field must never act as the Search button.
export function ReviewScreen({ review, fileName, onRestart }: Props) {
  const { id, ...initial } = review;
  const [values, setValues] = useState<Reviewed>(initial);
  const [newKeyword, setNewKeyword] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [stage, setStage] = useState<Stage>(null);
  const [results, setResults] = useState<Results | null>(null);
  const searching = stage === "searching";

  const update = (patch: Partial<Reviewed>) => setValues({ ...values, ...patch });

  // shortcut: polling never stops by itself (a hidden session, or a backend that lost the request, keeps asking), add a stop if the backend is ever not local.
  useEffect(() => {
    if (!searching) return;
    const timer = setInterval(async () => {
      try {
        const { stage: next } = await getStage(id);
        if (next === "done") setResults(await getResults(id));
        setError("");
        if (next !== "searching") setStage(next);
      } catch (err) {
        // The backend may still be searching, so keep the stage and poll again instead of giving up.
        setError(err instanceof Error ? err.message : String(err));
      }
    }, POLL_MS);
    return () => clearInterval(timer);
  }, [searching, id]);

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
      await startSearch(id, values);
      setResults(null); // only once the backend accepted the start, so a refusal keeps the old list
      setStage("searching");
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
          <button type="button" className="search" onClick={search} disabled={busy || searching}>
            Search
          </button>
        </div>
      </div>
      {error && <p role="alert" className="error">{error}</p>}
      {searching && <p role="status" className="note">Searching and checking jobs...</p>}
      {stage === "failed" && (
        <p role="alert" className="error">The search failed. Please press Search to try again.</p>
      )}
      {results && <JobList results={results} />}
      <div className="actions">
        <button type="button" className="secondary" onClick={onRestart}>
          Upload a different CV
        </button>
      </div>
    </section>
  );
}
