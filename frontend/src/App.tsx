import { BrowserRouter, Link, Route, Routes } from "react-router-dom";
import Dashboard from "./pages/Dashboard";
import LiveMeeting from "./pages/LiveMeeting";
import MeetingDetail from "./pages/MeetingDetail";
import Templates from "./pages/Templates";
import ConnectionStatus from "./components/ConnectionStatus";

export default function App() {
  return (
    <BrowserRouter>
      <div className="min-h-screen flex flex-col">
        <header className="border-b border-neutral-800 px-6 py-3 flex items-center gap-6">
          <Link to="/" className="text-lg font-semibold tracking-tight">
            Live Transcript Bot
          </Link>
          <nav className="flex gap-4 text-sm text-neutral-400">
            <Link to="/" className="hover:text-neutral-100">Dashboard</Link>
            <Link to="/templates" className="hover:text-neutral-100">Templates</Link>
          </nav>
          <div className="ml-auto">
            <ConnectionStatus />
          </div>
        </header>
        <main className="flex-1 min-h-0">
          <Routes>
            <Route path="/" element={<Dashboard />} />
            <Route path="/meetings/live/:id" element={<LiveMeeting />} />
            <Route path="/meetings/:id" element={<MeetingDetail />} />
            <Route path="/templates" element={<Templates />} />
          </Routes>
        </main>
      </div>
    </BrowserRouter>
  );
}
