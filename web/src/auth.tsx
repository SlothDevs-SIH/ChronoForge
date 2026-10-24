import { createContext, useCallback, useContext, useEffect, useState, type ReactNode } from "react";
import { Navigate, useLocation } from "react-router-dom";
import { api, session, type Role, type User } from "./api";

interface AuthState {
  user: User | null;
  /** true until the stored token has been checked once */
  loading: boolean;
  signIn: (email: string, password: string) => Promise<User>;
  signOut: () => void;
}

const AuthContext = createContext<AuthState>({ user: null, loading: true, signIn: async () => { throw new Error("no provider"); }, signOut: () => undefined });
export const useAuth = () => useContext(AuthContext);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [loading, setLoading] = useState(Boolean(session.get()));

  useEffect(() => {
    if (!session.get()) return;
    api.me().then(setUser).catch(() => session.clear()).finally(() => setLoading(false));
  }, []);

  useEffect(() => {
    const onOut = () => setUser(null);
    window.addEventListener("trueclose:signed-out", onOut);
    return () => window.removeEventListener("trueclose:signed-out", onOut);
  }, []);

  const signIn = useCallback(async (email: string, password: string) => {
    const { token, user: u } = await api.login(email, password);
    session.set(token);
    setUser(u);
    return u;
  }, []);
  const signOut = useCallback(() => { session.clear(); setUser(null); }, []);

  return <AuthContext.Provider value={{ user, loading, signIn, signOut }}>{children}</AuthContext.Provider>;
}

export const ROLE_LABEL: Record<Role, string> = { citizen: "Citizen", officer: "Municipal officer", admin: "Administrator" };

/** Where each role lands after sign-in. */
export const homeFor = (role: Role) => (role === "citizen" ? "/citizen" : role === "admin" ? "/admin" : "/dashboard");

/** UX guard only: the Agent service enforces the same rules on every request. */
export function RequireRole({ roles, children }: { roles: Role[]; children: ReactNode }) {
  const { user, loading } = useAuth();
  const loc = useLocation();
  if (loading) return <div className="loading-state auth-wait">Checking your session…</div>;
  if (!user) return <Navigate to={`/auth/login?next=${encodeURIComponent(loc.pathname + loc.search)}`} replace />;
  if (user.status === "pending") return <Pending />;
  if (!roles.includes(user.role)) return <Forbidden role={user.role} />;
  return <>{children}</>;
}

export function Pending() {
  const { signOut } = useAuth();
  return (
    <div className="auth-page"><div className="auth-card">
      <h1>Waiting for approval</h1>
      <p>Your officer account has been created. An administrator must approve it before you can see the triage queue or decide on approvals.</p>
      <button className="btn btn-secondary" onClick={signOut}>Sign out</button>
    </div></div>
  );
}

export function Forbidden({ role }: { role: Role }) {
  return (
    <div className="auth-page"><div className="auth-card">
      <h1>This page is not for your role</h1>
      <p>You are signed in as {ROLE_LABEL[role].toLowerCase()}. Your own workspace is one click away.</p>
      <a className="btn btn-primary" href={homeFor(role)}>Go to my dashboard</a>
    </div></div>
  );
}
