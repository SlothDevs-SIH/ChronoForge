import { useEffect, useState } from "react";
import { Link, NavLink, Outlet, Route, Routes, useLocation, useSearchParams } from "react-router-dom";
import Landing from "./pages/Landing";
import HowItWorks from "./pages/HowItWorks";
import Platform from "./pages/Platform";
import Triage from "./pages/Triage";
import TicketDetail from "./pages/TicketDetail";
import Approvals from "./pages/Approvals";
import Evaluation from "./pages/Evaluation";
import AuditLog from "./pages/AuditLog";
import type { Role } from "./api";
import { Login, Register } from "./pages/Auth";
import Citizen from "./pages/Citizen";
import Admin from "./pages/Admin";
import { RequireRole, ROLE_LABEL, useAuth } from "./auth";
import ConnectionBadge from "./components/ConnectionBadge";
import { Brand } from "./components/PublicNav";

const STAFF: Role[] = ["officer", "admin"];
const CITIES = ["bengaluru", "pune", "mumbai", "synthetic", "demo", "web"];

function AppShell() {
  const [params, setParams] = useSearchParams();
  const { user, signOut } = useAuth();
  const [open, setOpen] = useState(false);
  const loc = useLocation();
  useEffect(() => setOpen(false), [loc.pathname]);
  const city = params.get("city") ?? "";
  const q = city ? `?city=${city}` : "";
  const link = ({ isActive }: { isActive: boolean }) => (isActive ? "active" : "");
  const staff = user?.role === "officer" || user?.role === "admin";
  return (
    <div className="app-shell">
      <header className="app-topbar">
        <Brand />
        <button className="menu-toggle" aria-expanded={open} aria-controls="app-nav" onClick={() => setOpen(!open)}>{open ? "Close" : "Menu"}</button>
        <nav id="app-nav" className={`app-nav ${open ? "is-open" : ""}`} aria-label="Application">
          {user?.role === "citizen" && <NavLink to="/citizen" className={link}>My checks</NavLink>}
          {user?.role === "admin" && <NavLink to="/admin" className={link}>Administration</NavLink>}
          {staff && <>
            <NavLink to="/dashboard" className={link}>Overview</NavLink>
            <NavLink to={`/triage${q}`} className={link}>Triage queue</NavLink>
            <NavLink to="/approvals" className={link}>Approvals</NavLink>
            <NavLink to="/audit" className={link}>Audit log</NavLink>
          </>}
          <NavLink to="/evaluation" className={link}>Evaluation</NavLink>
          <NavLink to="/platform" className={link}>Platform</NavLink>
        </nav>
        <div className="app-actions">
          {staff && <ConnectionBadge />}
          {staff && <label className="city-control"><span>City</span>
            <select value={city} onChange={(e) => setParams(e.target.value ? { city: e.target.value } : {})}>
              <option value="">All cities</option>
              {CITIES.map((c) => <option key={c} value={c}>{c[0].toUpperCase() + c.slice(1)}</option>)}
            </select>
          </label>}
          {user && <span className="who"><span className="who-name">{user.name}</span><small>{ROLE_LABEL[user.role]}</small></span>}
          <button className="btn btn-secondary btn-sm" onClick={signOut}>Sign out</button>
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
      <Route path="/auth/login" element={<Login />} />
      <Route path="/auth/register" element={<Register />} />
      <Route element={<AppShell />}>
        <Route path="/citizen" element={<RequireRole roles={["citizen"]}><Citizen /></RequireRole>} />
        <Route path="/admin" element={<RequireRole roles={["admin"]}><Admin /></RequireRole>} />
        <Route path="/dashboard" element={<RequireRole roles={STAFF}><CityRoute overview /></RequireRole>} />
        <Route path="/triage" element={<RequireRole roles={STAFF}><CityRoute /></RequireRole>} />
        <Route path="/ticket/:id" element={<RequireRole roles={STAFF}><TicketDetail /></RequireRole>} />
        <Route path="/approvals" element={<RequireRole roles={STAFF}><Approvals /></RequireRole>} />
        <Route path="/audit" element={<RequireRole roles={STAFF}><AuditLog /></RequireRole>} />
      </Route>
      <Route path="*" element={<NotFound />} />
    </Routes>
  );
}
