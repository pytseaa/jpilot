import type { Review } from "./api";

/** One tab-local session. It stays empty until a CV is read, then it holds the review. */
export type Session = { key: string; review: Review | null; fileName: string | null };

type Props = {
  open: boolean;
  sessions: Session[];
  activeKey: string;
  onSelect: (key: string) => void;
  onNew: () => void;
};

export function Sidebar({ open, sessions, activeKey, onSelect, onNew }: Props) {
  return (
    <aside id="sidebar" className="sidebar" hidden={!open}>
      <button type="button" className="new-session" onClick={onNew}>
        + New Session
      </button>
      <nav aria-label="Sessions">
        <ul className="sessions">
          {sessions.map(
            (session) =>
              session.review && (
                <li key={session.key}>
                  <button
                    type="button"
                    aria-current={session.key === activeKey}
                    onClick={() => onSelect(session.key)}
                  >
                    {session.review.target_role}
                  </button>
                </li>
              ),
          )}
        </ul>
      </nav>
    </aside>
  );
}
