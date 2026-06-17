import { BrowserRouter, Link, Route, Routes } from "react-router-dom";
import Dashboard from "./pages/Dashboard";
import RecordingScreen from "./pages/RecordingScreen";
import RecordingDetail from "./pages/RecordingDetail";
import Templates from "./pages/Templates";
import People from "./pages/People";
import Ask from "./pages/Ask";
import ConnectionStatus from "./components/ConnectionStatus";

export default function App() {
  return (
    <BrowserRouter>
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
    </BrowserRouter>
  );
}
