import { useEffect, useState, type ReactNode } from "react";
import { BrowserRouter, Route, Routes } from "react-router-dom";
import { api } from "./lib/api";
import Dashboard from "./pages/Dashboard";
import RecordingScreen from "./pages/RecordingScreen";
import RecordingDetail from "./pages/RecordingDetail";
import Templates from "./pages/Templates";
import People from "./pages/People";
import Ask from "./pages/Ask";
import Settings from "./pages/Settings";
import Shell from "./components/Shell";
import ErrorBoundary from "./components/ErrorBoundary";
import mark from "./assets/sirina-mark.svg";

const STARTUP_TIMEOUT_MS = 45_000;

/** Branded paper-and-ink splash. Shows the startup phase, or an actionable error + retry. */
function Splash({ failed, elapsed, onRetry }: { failed: boolean; elapsed: number; onRetry: () => void }) {
  return (
    <div className="min-h-screen flex flex-col items-center justify-center gap-5 bg-paper text-ink">
      <img src={mark} alt="" className="w-16 h-16" />
      <div className="font-serif text-2xl font-semibold tracking-tight">Sirina</div>
      {failed ? (
        <div className="flex flex-col items-center gap-3">
          <p className="text-sm text-muted max-w-xs text-center leading-relaxed">
            Couldn't reach the backend — it may have failed to start. Check the logs in your data
            folder, then retry.
          </p>
          <button
            onClick={onRetry}
            className="px-4 h-9 rounded-field bg-signal-grad text-white text-sm font-semibold"
          >
            Retry
          </button>
        </div>
      ) : (
        <div className="flex flex-col items-center gap-3">
          <div className="w-6 h-6 rounded-full border-2 border-line-3 border-t-signal animate-spin motion-reduce:animate-none" />
          <p className="text-sm text-muted">Starting the backend…</p>
          {elapsed > 8 && (
            <p className="text-xs text-muted max-w-xs text-center leading-relaxed">
              First run downloads the transcription model — this can take a few minutes. ({elapsed}s)
            </p>
          )}
        </div>
      )}
    </div>
  );
}

/** Wait for the backend before rendering the app. Polls until it answers; after a timeout
 *  it surfaces an actionable error with retry instead of waiting forever. */
function BackendGate({ children }: { children: ReactNode }) {
  const [ready, setReady] = useState(false);
  const [elapsed, setElapsed] = useState(0);
  const [failed, setFailed] = useState(false);
  const [attempt, setAttempt] = useState(0);

  useEffect(() => {
    let alive = true;
    const t0 = Date.now();
    setFailed(false);
    setElapsed(0);
    const tick = async () => {
      try {
        await api.status();
        if (alive) setReady(true);
      } catch {
        if (!alive) return;
        setElapsed(Math.floor((Date.now() - t0) / 1000));
        if (Date.now() - t0 > STARTUP_TIMEOUT_MS) {
          setFailed(true); // give up; offer retry
          return;
        }
        setTimeout(tick, 1500);
      }
    };
    tick();
    return () => {
      alive = false;
    };
  }, [attempt]);

  if (ready) return <>{children}</>;
  return (
    <Splash
      failed={failed}
      elapsed={elapsed}
      onRetry={() => {
        setReady(false);
        setAttempt((a) => a + 1);
      }}
    />
  );
}

export default function App() {
  return (
    <BrowserRouter>
      <BackendGate>
        <Shell>
          <ErrorBoundary>
            <Routes>
              <Route path="/" element={<Dashboard />} />
              <Route path="/recordings/live/:id" element={<RecordingScreen />} />
              <Route path="/recordings/:id" element={<RecordingDetail />} />
              <Route path="/ask" element={<Ask />} />
              <Route path="/people" element={<People />} />
              <Route path="/templates" element={<Templates />} />
              <Route path="/settings" element={<Settings />} />
            </Routes>
          </ErrorBoundary>
        </Shell>
      </BackendGate>
    </BrowserRouter>
  );
}
