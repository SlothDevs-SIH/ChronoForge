import { Link, NavLink, Outlet, Route, Routes, useLocation, useSearchParams } from "react-router-dom";
import Landing from "./pages/Landing";
import HowItWorks from "./pages/HowItWorks";
import Platform from "./pages/Platform";
import Evaluation from "./pages/Evaluation";
import Triage from "./pages/Triage";
import TicketDetail from "./pages/TicketDetail";
import Approvals from "./pages/Approvals";
import AuditLog from "./pages/AuditLog";
import MyTickets, { MyTicket } from "./pages/MyTickets";
import Admin from "./pages/Admin";
import Hotspots from "./pages/Hotspots";
import Reply from "./pages/Reply";
import ConnectionBadge from "./components/ConnectionBadge";
import ErrorBoundary from "./components/ErrorBoundary";
import { Brand } from "./components/PublicNav";
import { useAuth } from "./auth/AuthProvider";
import { Forbidden, RequireAuth } from "./auth/guards";
import { ForgotPassword, Login, Pending, Register } from "./auth/AuthPages";

const CITIES = ["bengaluru", "pune", "mumbai", "synthetic", "demo", "web"];

function AppShell() {
  const [params, setParams] = useSearchParams();
  const { me, email, signOut, status } = useAuth();
  const location = useLocation();
  const city = params.get("city") ?? "";
  const link = ({ isActive }: { isActive: boolean }) => (isActive ? "active" : "");
  const staff = me?.role === "officer" || me?.role === "admin";
  return (
    <div className="app-shell">
      <header className="app-topbar">
        <Brand />
        <nav className="app-nav" aria-label="Application">
          {staff && <>
            <NavLink to="/dashboard" className={link}>Overview</NavLink>
            <NavLink to={`/triage${city ? `?city=${city}` : ""}`} className={link}>Triage queue</NavLink>
            <NavLink to="/approvals" className={link}>Approvals</NavLink>
            <NavLink to="/hotspots" className={link}>Repeat reopens</NavLink>
            <NavLink to="/audit" className={link}>Audit log</NavLink>
          </>}
          {me?.role === "admin" && <NavLink to="/admin" className={link}>Admin</NavLink>}
          {(me?.role === "citizen" || status === "disabled") && <NavLink to="/my-tickets" className={link}>My tickets</NavLink>}
        </nav>
        <div className="app-actions">
          {staff && <ConnectionBadge />}
          {staff && (
            <label className="city-control"><span>City</span>
              <select value={city} onChange={(e) => setParams(e.target.value ? { city: e.target.value } : {})}>
                <option value="">All cities</option>
                {CITIES.map((c) => <option key={c} value={c}>{c[0].toUpperCase() + c.slice(1)}</option>)}
              </select>
            </label>
          )}
          {status !== "disabled" && (
            <div className="whoami">
              <span title={email ?? ""}>{email}</span>
              <span className="role-chip">{me?.role}</span>
              <button type="button" className="btn btn-secondary btn-sm" onClick={() => void signOut()}>Sign out</button>
            </div>
          )}
        </div>
      </header>
      <main className="app-page"><ErrorBoundary resetKey={location.pathname}><Outlet /></ErrorBoundary></main>
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
      <div className="pub-cta"><Link className="btn btn-primary" to="/">Go to the home page</Link></div>
    </main></div>
  );
}

const STAFF = ["officer", "admin"] as const;

export default function App() {
  return (
    <Routes>
      <Route path="/" element={<Landing />} />
      <Route path="/how-it-works" element={<HowItWorks />} />
      <Route path="/platform" element={<Platform />} />
      <Route path="/evaluation" element={<Evaluation />} />
      <Route path="/reply/:token" element={<Reply />} />
      <Route path="/auth/login" element={<Login />} />
      <Route path="/auth/official" element={<Login mode="official" />} />
      <Route path="/auth/register" element={<Register />} />
      <Route path="/auth/forgot-password" element={<ForgotPassword />} />
      <Route path="/auth/pending" element={<Pending />} />
      <Route path="/forbidden" element={<Forbidden />} />
      <Route element={<RequireAuth><AppShell /></RequireAuth>}>
        <Route path="/dashboard" element={<RequireAuth roles={[...STAFF]}><CityRoute overview /></RequireAuth>} />
        <Route path="/triage" element={<RequireAuth roles={[...STAFF]}><CityRoute /></RequireAuth>} />
        <Route path="/ticket/:id" element={<RequireAuth roles={[...STAFF]}><TicketDetail /></RequireAuth>} />
        <Route path="/approvals" element={<RequireAuth roles={[...STAFF]}><Approvals /></RequireAuth>} />
        <Route path="/hotspots" element={<RequireAuth roles={[...STAFF]}><Hotspots /></RequireAuth>} />
        <Route path="/audit" element={<RequireAuth roles={[...STAFF]}><AuditLog /></RequireAuth>} />
        <Route path="/admin" element={<RequireAuth roles={["admin"]}><Admin /></RequireAuth>} />
        <Route path="/my-tickets" element={<RequireAuth roles={["citizen"]}><MyTickets /></RequireAuth>} />
        <Route path="/my-tickets/:id" element={<RequireAuth roles={["citizen"]}><MyTicket /></RequireAuth>} />
      </Route>
      <Route path="*" element={<NotFound />} />
    </Routes>
  );
}
