import { useEffect, useState, type ReactNode } from "react";
import { BrowserRouter, Link, Route, Routes } from "react-router-dom";
import { api } from "./lib/api";
import Dashboard from "./pages/Dashboard";
import RecordingScreen from "./pages/RecordingScreen";
import RecordingDetail from "./pages/RecordingDetail";
import Templates from "./pages/Templates";
import People from "./pages/People";
import Ask from "./pages/Ask";
import ConnectionStatus from "./components/ConnectionStatus";

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
    <div className="min-h-screen flex flex-col items-center justify-center gap-3 text-neutral-400">
      <div className="w-6 h-6 rounded-full border-2 border-neutral-700 border-t-rose-500 animate-spin" />
      <p className="text-sm">Starting the backend…</p>
      {elapsed > 8 && (
        <p className="text-xs text-neutral-500 max-w-xs text-center leading-relaxed">
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
        <div className="min-h-screen flex flex-col">
          <header className="border-b border-neutral-800 px-6 py-3 flex items-center gap-6">
            <Link to="/" className="text-lg font-semibold tracking-tight">
              Meeting Recorder
            </Link>
            <nav className="flex gap-4 text-sm text-neutral-400">
              <Link to="/" className="hover:text-neutral-100">Dashboard</Link>
              <Link to="/ask" className="hover:text-neutral-100">Ask</Link>
              <Link to="/people" className="hover:text-neutral-100">People</Link>
              <Link to="/templates" className="hover:text-neutral-100">Templates</Link>
            </nav>
            <div className="ml-auto">
              <ConnectionStatus />
            </div>
          </header>
          <main className="flex-1 min-h-0">
            <Routes>
              <Route path="/" element={<Dashboard />} />
              <Route path="/recordings/live/:id" element={<RecordingScreen />} />
              <Route path="/recordings/:id" element={<RecordingDetail />} />
              <Route path="/ask" element={<Ask />} />
              <Route path="/people" element={<People />} />
              <Route path="/templates" element={<Templates />} />
            </Routes>
          </main>
        </div>
      </BackendGate>
    </BrowserRouter>
  );
}
