import { Link, NavLink, Outlet, Route, Routes, useSearchParams } from "react-router-dom";
import Landing from "./pages/Landing";
import HowItWorks from "./pages/HowItWorks";
import Platform from "./pages/Platform";
import Triage from "./pages/Triage";
import TicketDetail from "./pages/TicketDetail";
import Approvals from "./pages/Approvals";
import Evaluation from "./pages/Evaluation";
import AuditLog from "./pages/AuditLog";
import ConnectionBadge from "./components/ConnectionBadge";
import { Brand } from "./components/PublicNav";

const CITIES = ["bengaluru", "pune", "mumbai", "synthetic", "demo"];

function AppShell() {
  const [params, setParams] = useSearchParams();
  const city = params.get("city") ?? "";
  const link = ({ isActive }: { isActive: boolean }) => (isActive ? "active" : "");
  return (
    <div className="app-shell">
      <header className="app-topbar">
        <Brand />
        <nav className="app-nav" aria-label="Application">
          <NavLink to="/dashboard" className={link}>Overview</NavLink>
          <NavLink to={`/triage${city ? `?city=${city}` : ""}`} className={link}>Triage queue</NavLink>
          <NavLink to="/approvals" className={link}>Approvals</NavLink>
          <NavLink to="/audit" className={link}>Audit log</NavLink>
          <NavLink to="/evaluation" className={link}>Evaluation</NavLink>
          <NavLink to="/platform" className={link}>Platform</NavLink>
        </nav>
        <div className="app-actions">
          <ConnectionBadge />
          <label className="city-control"><span>City</span>
            <select value={city} onChange={(e) => setParams(e.target.value ? { city: e.target.value } : {})}>
              <option value="">All cities</option>
              {CITIES.map((c) => <option key={c} value={c}>{c[0].toUpperCase() + c.slice(1)}</option>)}
            </select>
          </label>
        </div>
      </header>
      <main className="app-page"><Outlet context={{ city }} /></main>
    </div>
  );
}

function CityRoute({ overview = false }: { overview?: boolean }) {
  const [params] = useSearchParams();
  return <Triage city={params.get("city") ?? ""} overview={overview} />;
}

function NotFound() {
  return (
    <div className="pub-page"><main className="pub-main not-found">
      <h1>This page doesn't exist</h1>
      <p>The address may be mistyped or the page may have moved.</p>
      <div className="pub-cta"><Link className="btn btn-primary" to="/">Go to the home page</Link><Link className="btn btn-secondary" to="/dashboard">Open the app</Link></div>
    </main></div>
  );
}

export default function App() {
  return (
    <Routes>
      <Route path="/" element={<Landing />} />
      <Route path="/how-it-works" element={<HowItWorks />} />
      <Route path="/platform" element={<Platform />} />
      <Route path="/evaluation" element={<Evaluation />} />
      <Route element={<AppShell />}>
        <Route path="/dashboard" element={<CityRoute overview />} />
        <Route path="/triage" element={<CityRoute />} />
        <Route path="/ticket/:id" element={<TicketDetail />} />
        <Route path="/approvals" element={<Approvals />} />
        <Route path="/audit" element={<AuditLog />} />
      </Route>
      <Route path="*" element={<NotFound />} />
    </Routes>
  );
}
