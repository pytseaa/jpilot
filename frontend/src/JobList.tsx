import type { Results } from "./api";

// An ad link comes from a third party, so only a web address becomes a link.
const isWebLink = (link: string | null): link is string => !!link && /^https?:\/\//i.test(link);

// Words, not colour alone, tell the two grades apart.
const GRADE_LABEL = { 1: "Plausible fit", 2: "Strong fit" };

/** The shortlist: up to five jobs the backend graded 1 or 2, each with the claims whose quotes it found. */
export function JobList({ results }: { results: Results }) {
  const { jobs, dropped_claims } = results;
  return (
    <section>
      {jobs.length === 0 ? (
        <p role="status" className="note">Done. No job had a fit with quotes we could check.</p>
      ) : (
        <p role="status" className="note">
          Done. {jobs.length} {jobs.length === 1 ? "job fits" : "jobs fit"} your CV, strongest fit first.
        </p>
      )}
      <ol className="jobs">
        {jobs.map((job) => {
          const title = job.title || "Untitled job";
          return (
            <li key={job.job_id}>
              <strong>
                {isWebLink(job.apply_link) ? (
                  <a href={job.apply_link} target="_blank" rel="noreferrer">{title}</a>
                ) : (
                  title
                )}
              </strong>
              <span className={`grade grade-${job.grade}`}>{GRADE_LABEL[job.grade]}</span>
              {job.unverified && <span className="unverified">Unverified</span>}
              <div className="note">{[job.employer, job.location].filter(Boolean).join(" · ")}</div>
              <div className="note">
                Collected {job.collected} · {job.posted_date ? `Posted ${job.posted_date}` : "posted date not given"}
              </div>
              {job.claims.map((claim, i) => (
                <div className="claim" key={i}>
                  <strong>{claim.requirement}</strong>
                  <blockquote><span className="source">Your CV</span> &ldquo;{claim.cv_quote}&rdquo;</blockquote>
                  <blockquote><span className="source">The ad</span> &ldquo;{claim.job_quote}&rdquo;</blockquote>
                </div>
              ))}
              <p className="note">Check the ad before you apply: the job may have closed.</p>
            </li>
          );
        })}
      </ol>
      {jobs.some((job) => job.unverified) && (
        <p className="note">
          Unverified: the ad does not say clearly where the job is or what type it is. Check the ad.
        </p>
      )}
      {dropped_claims > 0 && (
        <p className="note">
          {dropped_claims} {dropped_claims === 1 ? "claim was" : "claims were"} left out because
          {dropped_claims === 1 ? " its" : " their"} quotes were not found in your CV or the ad.
        </p>
      )}
    </section>
  );
}
