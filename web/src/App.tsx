import { Link, Route, Routes, useSearchParams } from "react-router-dom";
import Triage from "./pages/Triage";
import TicketDetail from "./pages/TicketDetail";
import Approvals from "./pages/Approvals";

const CITIES = ["", "bengaluru", "pune", "mumbai", "synthetic", "demo"];

export default function App() {
  const [params, setParams] = useSearchParams();
  const city = params.get("city") ?? "";
  return (
    <>
      <header className="topbar">
        <span className="brand">TrueClose</span>
        <Link to={`/?city=${city}`}>Triage</Link>
        <Link to="/approvals">Approvals</Link>
        <select value={city} onChange={(e) => setParams(e.target.value ? { city: e.target.value } : {})} aria-label="City">
          {CITIES.map((c) => <option key={c} value={c}>{c || "All cities"}</option>)}
        </select>
      </header>
      <main className="page">
        <Routes>
          <Route path="/" element={<Triage city={city} />} />
          <Route path="/ticket/:id" element={<TicketDetail />} />
          <Route path="/approvals" element={<Approvals />} />
        </Routes>
      </main>
    </>
  );
}
