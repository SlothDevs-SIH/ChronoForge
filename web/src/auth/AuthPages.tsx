import { useId, useState, type FormEvent, type ReactNode } from "react";
import { Link, Navigate, useNavigate, useSearchParams } from "react-router-dom";
import Icon from "../components/Icon";
import { useAuth } from "./AuthProvider";
import { homeFor } from "./guards";

type Mode = "citizen" | "official";

function Shell({ title, lead, children }: { title: string; lead?: string; children: ReactNode }) {
  return (
    <div className="auth-page">
      <aside className="auth-art" aria-hidden="true"><span className="brand brand-light"><span className="brand-mark"><Icon name="leaf" size={20} /></span><strong>TrueClose</strong></span></aside>
      <main className="auth-main">
        <div className="auth-card">
          <Link className="auth-back" to="/">Back to home</Link>
          <h1>{title}</h1>
          {lead && <p className="auth-lead">{lead}</p>}
          {children}
        </div>
      </main>
    </div>
  );
}

function Field({ label, error, children, id }: { label: string; error?: string | null; children: ReactNode; id: string }) {
  return <div className="field"><label htmlFor={id}>{label}</label>{children}{error && <p className="field-error" id={`${id}-err`} role="alert">{error}</p>}</div>;
}

function PasswordInput({ id, value, onChange, autoComplete, describedBy }: { id: string; value: string; onChange: (v: string) => void; autoComplete: string; describedBy?: string }) {
  const [show, setShow] = useState(false);
  return (
    <div className="pw">
      <input id={id} type={show ? "text" : "password"} value={value} onChange={(e) => onChange(e.target.value)} autoComplete={autoComplete} required minLength={8} aria-describedby={describedBy} />
      <button type="button" className="pw-toggle" onClick={() => setShow((s) => !s)} aria-label={show ? "Hide password" : "Show password"} aria-pressed={show}><Icon name={show ? "eye-off" : "eye"} size={18} /></button>
    </div>
  );
}

/** After a successful sign-in, send people where they were going if it is safe, otherwise to their own page. */
export function safeNext(next: string | null): string | null {
  return next && next.startsWith("/") && !next.startsWith("//") && !next.startsWith("/auth") ? next : null;
}

export function Login({ mode = "citizen" }: { mode?: Mode }) {
  const { signIn, status, me, sessionExpired, clearExpired } = useAuth();
  const [params] = useSearchParams();
  const nav = useNavigate();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const ids = { e: useId(), p: useId() };
  const next = safeNext(params.get("next"));
  const official = mode === "official";

  if (status === "authenticated" && me?.status === "active") return <Navigate to={next ?? homeFor(me.role)} replace />;
  if (status === "authenticated" && me?.status === "pending") return <Navigate to="/auth/pending" replace />;

  async function submit(e: FormEvent) {
    e.preventDefault();
    setBusy(true); setError(null);
    try { await signIn(email.trim(), password); clearExpired(); nav(next ?? "/dashboard", { replace: true }); }
    catch (err) { setError((err as Error).message); }
    finally { setBusy(false); }
  }

  return (
    <Shell title={official ? "Official sign-in" : "Sign in"} lead={official ? "For municipal officers and TrueClose administrators. Officer accounts are approved by an administrator." : "See the status of the complaint tickets linked to you."}>
      {(params.get("expired") === "1" || sessionExpired) && <p className="auth-note" role="status">Your session ended. Sign in again to continue.</p>}
      {status === "unconfigured" && <p className="auth-note auth-note-warn" role="alert">Sign-in isn't set up on this site yet.</p>}
      <form onSubmit={submit} noValidate={false}>
        <Field label="Email" id={ids.e}><input id={ids.e} type="email" value={email} onChange={(e) => setEmail(e.target.value)} autoComplete="email" required /></Field>
        <Field label="Password" id={ids.p} error={error}><PasswordInput id={ids.p} value={password} onChange={setPassword} autoComplete="current-password" describedBy={error ? `${ids.p}-err` : undefined} /></Field>
        <div className="auth-row"><Link className="text-link" to="/auth/forgot-password">Forgot your password?</Link></div>
        <button className="btn btn-primary auth-submit" type="submit" disabled={busy || status === "unconfigured"}>{busy ? "Signing in…" : "Sign in"}</button>
      </form>
      <p className="auth-alt">
        {official ? <>Looking for the citizen sign-in? <Link className="text-link" to="/auth/login">Sign in as a citizen</Link></>
          : <>New here? <Link className="text-link" to="/auth/register">Create an account</Link>. Officer? <Link className="text-link" to="/auth/official">Official sign-in</Link></>}
      </p>
    </Shell>
  );
}

export function Register() {
  const { signUp, status } = useAuth();
  const [params] = useSearchParams();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [officer, setOfficer] = useState(params.get("role") === "officer");
  const [error, setError] = useState<string | null>(null);
  const [done, setDone] = useState<null | { needsConfirmation: boolean }>(null);
  const [busy, setBusy] = useState(false);
  const ids = { e: useId(), p: useId() };

  async function submit(e: FormEvent) {
    e.preventDefault();
    setBusy(true); setError(null);
    try { setDone(await signUp(email.trim(), password, officer ? "officer" : "citizen")); }
    catch (err) { setError((err as Error).message); }
    finally { setBusy(false); }
  }

  if (done) {
    return (
      <Shell title="Check your email">
        <p>{done.needsConfirmation ? "We sent a confirmation link to your email. Open it, then sign in." : "Your account is ready."}</p>
        {officer && <p className="auth-note" role="status">Officer accounts need approval from an administrator before they can open the dashboard. You can sign in now; you'll see a waiting screen until you're approved.</p>}
        {!officer && <p className="auth-note" role="status">Citizen accounts show the tickets an administrator has linked to you. You'll see none until one is linked.</p>}
        <p className="auth-alt"><Link className="text-link" to="/auth/login">Go to sign in</Link></p>
      </Shell>
    );
  }
  return (
    <Shell title="Create an account" lead="Citizens can see the complaint tickets linked to them. Officers are approved by an administrator.">
      {status === "unconfigured" && <p className="auth-note auth-note-warn" role="alert">Sign-in isn't set up on this site yet.</p>}
      <form onSubmit={submit}>
        <Field label="Email" id={ids.e}><input id={ids.e} type="email" value={email} onChange={(e) => setEmail(e.target.value)} autoComplete="email" required /></Field>
        <Field label="Password (at least 8 characters)" id={ids.p} error={error}><PasswordInput id={ids.p} value={password} onChange={setPassword} autoComplete="new-password" describedBy={error ? `${ids.p}-err` : undefined} /></Field>
        <label className="check"><input type="checkbox" checked={officer} onChange={(e) => setOfficer(e.target.checked)} /> I'm a municipal officer and need dashboard access (an administrator must approve this)</label>
        <button className="btn btn-primary auth-submit" type="submit" disabled={busy || status === "unconfigured"}>{busy ? "Creating…" : "Create account"}</button>
      </form>
      <p className="auth-alt">Already registered? <Link className="text-link" to="/auth/login">Sign in</Link></p>
    </Shell>
  );
}

export function ForgotPassword() {
  const { requestPasswordReset, status } = useAuth();
  const [email, setEmail] = useState("");
  const [sent, setSent] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const id = useId();
  async function submit(e: FormEvent) {
    e.preventDefault();
    setBusy(true); setError(null);
    try { await requestPasswordReset(email.trim()); setSent(true); }
    catch (err) { setError((err as Error).message); }
    finally { setBusy(false); }
  }
  return (
    <Shell title="Reset your password" lead="Enter your email and we'll send a link to choose a new password.">
      {sent ? <p className="auth-note" role="status">If an account exists for that email, a reset link is on its way.</p> : (
        <form onSubmit={submit}>
          <Field label="Email" id={id} error={error}><input id={id} type="email" value={email} onChange={(e) => setEmail(e.target.value)} autoComplete="email" required /></Field>
          <button className="btn btn-primary auth-submit" type="submit" disabled={busy || status === "unconfigured"}>{busy ? "Sending…" : "Send reset link"}</button>
        </form>
      )}
      <p className="auth-alt"><Link className="text-link" to="/auth/login">Back to sign in</Link></p>
    </Shell>
  );
}

export function Pending() {
  const { me, refreshProfile, signOut, status } = useAuth();
  const [checking, setChecking] = useState(false);
  if (status === "authenticated" && me?.status === "active") return <Navigate to={homeFor(me.role)} replace />;
  if (status === "anonymous") return <Navigate to="/auth/login" replace />;
  return (
    <Shell title="Waiting for approval" lead="An administrator needs to approve your officer account before you can open the dashboard.">
      <p className="auth-note" role="status">You'll get access as soon as it's approved. Nothing else is needed from you.</p>
      <div className="auth-actions">
        <button type="button" className="btn btn-primary" disabled={checking} onClick={async () => { setChecking(true); await refreshProfile(); setChecking(false); }}>{checking ? "Checking…" : "Check again"}</button>
        <button type="button" className="btn btn-secondary" onClick={() => void signOut()}>Sign out</button>
      </div>
    </Shell>
  );
}
