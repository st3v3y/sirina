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

/** Wait for the backend before rendering the app. In the packaged desktop app the
 *  bundled backend takes a while to start on first run (binary extraction + the
 *  transcription model downloads), so we poll until it answers instead of erroring. */
function BackendGate({ children }: { children: ReactNode }) {
  const [ready, setReady] = useState(false);
  const [elapsed, setElapsed] = useState(0);

  useEffect(() => {
    let alive = true;
    const t0 = Date.now();
    const tick = async () => {
      try {
        await api.status();
        if (alive) setReady(true);
      } catch {
        if (!alive) return;
        setElapsed(Math.floor((Date.now() - t0) / 1000));
        setTimeout(tick, 1500);
      }
    };
    tick();
    return () => {
      alive = false;
    };
  }, []);

  if (ready) return <>{children}</>;
  return (
    <div className="min-h-screen flex flex-col items-center justify-center gap-3 text-muted">
      <div className="w-6 h-6 rounded-full border-2 border-line-3 border-t-signal animate-spin" />
      <p className="text-sm">Starting the backend…</p>
      {elapsed > 8 && (
        <p className="text-xs text-muted max-w-xs text-center leading-relaxed">
          First run downloads the transcription model — this can take a few minutes. ({elapsed}s)
        </p>
      )}
    </div>
  );
}

export default function App() {
  return (
    <BrowserRouter>
      <BackendGate>
        <Shell>
          <Routes>
            <Route path="/" element={<Dashboard />} />
            <Route path="/recordings/live/:id" element={<RecordingScreen />} />
            <Route path="/recordings/:id" element={<RecordingDetail />} />
            <Route path="/ask" element={<Ask />} />
            <Route path="/people" element={<People />} />
            <Route path="/templates" element={<Templates />} />
            <Route path="/settings" element={<Settings />} />
          </Routes>
        </Shell>
      </BackendGate>
    </BrowserRouter>
  );
}
