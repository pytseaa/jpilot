import { useState } from "react";
import type { Review } from "./api";
import { ReviewScreen } from "./ReviewScreen";
import { Sidebar, type Session } from "./Sidebar";
import { UploadForm } from "./UploadForm";

const emptySession = (): Session => ({ key: crypto.randomUUID(), review: null });

export function App() {
  const [sessions, setSessions] = useState<Session[]>(() => [emptySession()]);
  const [activeKey, setActiveKey] = useState(sessions[0].key);
  const [sidebarOpen, setSidebarOpen] = useState(true);

  // An empty session already is a new session, so reuse it instead of piling up blank ones.
  const startSession = () => {
    const empty = sessions.find((s) => !s.review);
    if (empty) return setActiveKey(empty.key);
    const fresh = emptySession();
    setSessions([...sessions, fresh]);
    setActiveKey(fresh.key);
  };

  // Functional update: this runs after an upload finishes, when `sessions` may have changed.
  const cvRead = (key: string, review: Review) =>
    setSessions((list) => list.map((s) => (s.key === key ? { ...s, review } : s)));

  return (
    <div className="app">
      <Sidebar
        open={sidebarOpen}
        sessions={sessions}
        activeKey={activeKey}
        onSelect={setActiveKey}
        onNew={startSession}
      />
      <div className="panel">
        <header className="topbar">
          <button
            type="button"
            className="menu-toggle"
            aria-label={sidebarOpen ? "Hide sidebar" : "Show sidebar"}
            aria-expanded={sidebarOpen}
            aria-controls="sidebar"
            onClick={() => setSidebarOpen(!sidebarOpen)}
          >
            &#9776;
          </button>
          <span className="brand">JobPilot</span>
        </header>
        {/* Every session stays mounted and only the active one is shown, so edits survive switching. */}
        <main>
          {sessions.map((s) => (
            <div key={s.key} hidden={s.key !== activeKey}>
              {s.review ? (
                <ReviewScreen review={s.review} onRestart={startSession} />
              ) : (
                <UploadForm onRead={(review) => cvRead(s.key, review)} />
              )}
            </div>
          ))}
        </main>
      </div>
    </div>
  );
}
