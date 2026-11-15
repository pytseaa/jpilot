import type { ResultJob } from "./api";

// An ad link comes from a third party, so only a web address becomes a link.
const isWebLink = (link: string | null): link is string => !!link && /^https?:\/\//i.test(link);

/** The interim results: the qualifying jobs, already in keyword order. */
export function JobList({ jobs }: { jobs: ResultJob[] }) {
  if (jobs.length === 0) {
    return <p role="status" className="note">Done. No job matched your keywords.</p>;
  }
  return (
    <section>
      <p role="status" className="note">
        Done. {jobs.length} {jobs.length === 1 ? "job matches" : "jobs match"} your keywords, best match first.
      </p>
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
              {job.unverified && <span className="unverified">Unverified</span>}
              <div className="note">{[job.employer, job.location].filter(Boolean).join(" · ")}</div>
            </li>
          );
        })}
      </ol>
      {jobs.some((job) => job.unverified) && (
        <p className="note">
          Unverified: the ad does not say clearly where the job is or what type it is. Check the ad.
        </p>
      )}
    </section>
  );
}
