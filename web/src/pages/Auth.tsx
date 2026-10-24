import { useState, type FormEvent, type ReactNode } from "react";
import { Link, Navigate, useNavigate, useSearchParams } from "react-router-dom";
import { api } from "../api";
import { homeFor, useAuth } from "../auth";
import { Brand } from "../components/PublicNav";

function Shell({ title, lede, children, foot }: { title: string; lede: string; children: ReactNode; foot: ReactNode }) {
  return (
    <div className="auth-page">
      <div className="auth-card">
        <Brand />
        <h1>{title}</h1>
        <p className="muted">{lede}</p>
        {children}
        <p className="auth-foot">{foot}</p>
      </div>
    </div>
  );
}

// The API client throws the server's message for 4xx answers, and "502 Bad Gateway" style text when the service is down.
const friendly = (err: unknown, fallback: string) => (err instanceof Error && !/^\d{3}\b/.test(err.message) ? err.message : fallback);

export function Login() {
  const { user, signIn } = useAuth();
  const [params] = useSearchParams();
  const nav = useNavigate();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  if (user) return <Navigate to={homeFor(user.role)} replace />;

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    setBusy(true); setError("");
    try {
      const u = await signIn(email, password);
      const next = params.get("next");
      nav(next && next.startsWith("/") && !next.startsWith("//") ? next : homeFor(u.role), { replace: true });
    } catch (err) {
      setError(friendly(err, "Could not reach the sign-in service. Try again in a moment."));
    } finally { setBusy(false); }
  };

  return (
    <Shell title="Sign in" lede="Citizens, municipal officers and administrators each get their own workspace." foot={<>New here? <Link to="/auth/register">Create an account</Link></>}>
      <form onSubmit={submit} className="auth-form" noValidate>
        <label htmlFor="email">Email</label>
        <input id="email" type="email" autoComplete="email" required value={email} onChange={(e) => setEmail(e.target.value)} />
        <label htmlFor="password">Password</label>
        <input id="password" type="password" autoComplete="current-password" required value={password} onChange={(e) => setPassword(e.target.value)} />
        {error && <div className="auth-error" role="alert">{error}</div>}
        <button className="btn btn-primary" disabled={busy || !email || !password}>{busy ? "Signing in…" : "Sign in"}</button>
      </form>
    </Shell>
  );
}

export function Register() {
  const { user, signIn } = useAuth();
  const nav = useNavigate();
  const [role, setRole] = useState<"citizen" | "officer">("citizen");
  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  if (user) return <Navigate to={homeFor(user.role)} replace />;

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    setBusy(true); setError("");
    try {
      await api.register(email, name, password, role);
      const u = await signIn(email, password);
      nav(homeFor(u.role), { replace: true });
    } catch (err) {
      setError(friendly(err, "Could not reach the sign-up service. Try again in a moment."));
    } finally { setBusy(false); }
  };

  return (
    <Shell title="Create an account" lede="Pick the workspace you need. Officer accounts are checked by an administrator before they get access." foot={<>Already registered? <Link to="/auth/login">Sign in</Link></>}>
      <form onSubmit={submit} className="auth-form" noValidate>
        <fieldset className="role-pick">
          <legend>I am a</legend>
          <label className={role === "citizen" ? "is-on" : ""}><input type="radio" name="role" checked={role === "citizen"} onChange={() => setRole("citizen")} /><strong>Citizen</strong><small>Follow checks on complaints I filed</small></label>
          <label className={role === "officer" ? "is-on" : ""}><input type="radio" name="role" checked={role === "officer"} onChange={() => setRole("officer")} /><strong>Municipal officer</strong><small>Needs administrator approval</small></label>
        </fieldset>
        <label htmlFor="name">Full name</label>
        <input id="name" autoComplete="name" required value={name} onChange={(e) => setName(e.target.value)} />
        <label htmlFor="email">Email</label>
        <input id="email" type="email" autoComplete="email" required value={email} onChange={(e) => setEmail(e.target.value)} />
        <label htmlFor="password">Password <small>at least 8 characters</small></label>
        <input id="password" type="password" autoComplete="new-password" minLength={8} required value={password} onChange={(e) => setPassword(e.target.value)} />
        {error && <div className="auth-error" role="alert">{error}</div>}
        <button className="btn btn-primary" disabled={busy || !email || !name || password.length < 8}>{busy ? "Creating…" : "Create account"}</button>
      </form>
    </Shell>
  );
}
