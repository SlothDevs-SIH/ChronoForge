import type { ReactNode } from "react";
import { Link, Navigate, useLocation } from "react-router-dom";
import { useAuth } from "./AuthProvider";
import type { Role } from "../types";

/** Where each role lands after signing in. */
export const homeFor = (role: Role | undefined) => (role === "citizen" ? "/my-tickets" : "/dashboard");

function Screen({ title, children }: { title: string; children: ReactNode }) {
  return (
    <div className="pub-page"><main className="pub-main not-found">
      <h1>{title}</h1>
      {children}
    </main></div>
  );
}

export function Forbidden() {
  const { me } = useAuth();
  return (
    <Screen title="You don't have access to this page">
      <p>Your account can't open it. If you think it should, ask an administrator to check your role.</p>
      <div className="pub-cta"><Link className="btn btn-primary" to={homeFor(me?.role)}>Go to your page</Link></div>
    </Screen>
  );
}

/**
 * Route guard. Frontend guards are only for a sensible experience: both services check the token and the role on every
 * request. Order: not set up, loading, signed out (to login with ?next), profile problems, pending approval, wrong role.
 */
export function RequireAuth({ roles, children }: { roles?: Role[]; children: ReactNode }) {
  const { status, me, profileError, sessionExpired } = useAuth();
  const loc = useLocation();
  if (status === "disabled") return <>{children}</>;
  if (status === "unconfigured") {
    return <Screen title="Sign-in isn't set up yet"><p>This site was deployed without its sign-in settings. An administrator needs to add them before anyone can sign in.</p></Screen>;
  }
  if (status === "loading") return <div className="loading-state" role="status">Checking your session…</div>;
  if (status === "anonymous") {
    const next = encodeURIComponent(loc.pathname + loc.search);
    return <Navigate to={`/auth/login?next=${next}${sessionExpired ? "&expired=1" : ""}`} replace />;
  }
  if (!me) {
    return <Screen title="We couldn't load your account"><p>{profileError ?? "Try again in a moment."}</p><div className="pub-cta"><button type="button" className="btn btn-primary" onClick={() => window.location.reload()}>Try again</button></div></Screen>;
  }
  if (me.status === "pending") return <Navigate to="/auth/pending" replace />;
  if (me.status === "rejected") return <Screen title="Your account wasn't approved"><p>An administrator declined this request. If that's a mistake, contact the team that invited you.</p></Screen>;
  if (roles && !roles.includes(me.role)) return me.role === "citizen" && roles.includes("officer") ? <Navigate to="/my-tickets" replace /> : <Forbidden />;
  return <>{children}</>;
}
