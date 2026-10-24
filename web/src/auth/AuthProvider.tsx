import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState, type ReactNode } from "react";
import { createClient, type Session, type SupabaseClient } from "@supabase/supabase-js";
import { api } from "../api";
import { onUnauthorized, setTokenProvider, userMessage } from "../lib/http";
import type { Me } from "../types";

// "loading": checking for a saved session. "anonymous": signed out. "authenticated": signed in, profile loaded (or failed:
// see profileError). "disabled": local demo with AUTH_REQUIRED=0 on the backends, no sign-in. "unconfigured": production
// build without Supabase settings, so sign-in cannot work and the app says so instead of pretending.
export type AuthStatus = "loading" | "anonymous" | "authenticated" | "disabled" | "unconfigured";

interface AuthValue {
  status: AuthStatus;
  me: Me | null;
  email: string | null;
  profileError: string | null;
  sessionExpired: boolean;
  signIn: (email: string, password: string) => Promise<void>;
  signUp: (email: string, password: string, requestedRole: "citizen" | "officer") => Promise<{ needsConfirmation: boolean }>;
  signOut: () => Promise<void>;
  requestPasswordReset: (email: string) => Promise<void>;
  refreshProfile: () => Promise<void>;
  clearExpired: () => void;
}

const Ctx = createContext<AuthValue | null>(null);
export function useAuth(): AuthValue {
  const v = useContext(Ctx);
  if (!v) throw new Error("useAuth must be used inside AuthProvider");
  return v;
}

const SUPABASE_URL = import.meta.env.VITE_SUPABASE_URL || import.meta.env.NEXT_PUBLIC_SUPABASE_URL;
const SUPABASE_KEY = import.meta.env.VITE_SUPABASE_ANON_KEY || import.meta.env.NEXT_PUBLIC_SUPABASE_ANON_KEY;
const DISABLED = import.meta.env.VITE_AUTH_DISABLED === "1";

const LOCAL_ME: Me = { user_id: "local", email: "local demo", role: "admin", status: "active", requested_role: null, ticket_ids: [] };

/** Friendlier text for Supabase auth errors. */
function authMessage(err: unknown): string {
  const m = String((err as { message?: string })?.message ?? err ?? "");
  if (/invalid login credentials/i.test(m)) return "That email and password don't match. Check them and try again.";
  if (/email not confirmed/i.test(m)) return "Confirm your email first. We sent you a link when you registered.";
  if (/already registered|already been registered/i.test(m)) return "An account with this email already exists. Sign in instead.";
  if (/password.*(short|least|weak)/i.test(m)) return "Choose a longer password (at least 8 characters).";
  if (/rate limit|too many/i.test(m)) return "Too many attempts. Wait a minute and try again.";
  if (/fetch|network/i.test(m)) return "Can't reach the sign-in service. Check your connection and try again.";
  return m || "Something went wrong. Try again.";
}

export function AuthProvider({ children, client }: { children: ReactNode; client?: SupabaseClient | null }) {
  const supabase = useMemo<SupabaseClient | null>(
    () => client !== undefined ? client : (SUPABASE_URL && SUPABASE_KEY ? createClient(SUPABASE_URL, SUPABASE_KEY, { auth: { persistSession: true, autoRefreshToken: true } }) : null),
    [client]);
  const [session, setSession] = useState<Session | null>(null);
  const [me, setMe] = useState<Me | null>(null);
  const [profileError, setProfileError] = useState<string | null>(null);
  const [checked, setChecked] = useState(false);
  const ready = !supabase || checked;
  const [expired, setExpired] = useState(false);
  const sessionRef = useRef<Session | null>(null);
  useEffect(() => { sessionRef.current = session; }, [session]);

  // Both services get the current access token on every request.
  useEffect(() => {
    setTokenProvider(async () => {
      if (!supabase) return null;
      const { data } = await supabase.auth.getSession();
      return data.session?.access_token ?? null;
    });
  }, [supabase]);

  const loadProfile = useCallback(async (s: Session | null) => {
    if (!s) { setMe(null); setProfileError(null); return; }
    try {
      let profile = await api.me();
      // An officer account asks for the role at sign-up; the request is only a request, an admin decides.
      const asked = (s.user.user_metadata as { requested_role?: string } | undefined)?.requested_role;
      if (asked === "officer" && profile.role === "citizen" && profile.status === "active" && !profile.requested_role) {
        profile = await api.setProfile("officer");
      }
      setMe(profile);
      setProfileError(null);
    } catch (e) {
      setMe(null);
      setProfileError(userMessage(e));
    }
  }, []);

  useEffect(() => {
    if (!supabase) return;
    let live = true;
    void supabase.auth.getSession().then(async ({ data }) => { if (!live) return; setSession(data.session); await loadProfile(data.session); if (live) setChecked(true); });
    const { data: sub } = supabase.auth.onAuthStateChange((_event, s) => { setSession(s); void loadProfile(s); });
    return () => { live = false; sub.subscription.unsubscribe(); };
  }, [supabase, loadProfile]);

  // A 401 on a request that carried a token means the session is no longer valid.
  useEffect(() => onUnauthorized(() => {
    if (!sessionRef.current || !supabase) return;
    setExpired(true);
    void supabase.auth.signOut();
  }), [supabase]);

  const value = useMemo<AuthValue>(() => {
    let status: AuthStatus;
    if (DISABLED) status = "disabled";
    else if (!supabase) status = "unconfigured";
    else if (!ready) status = "loading";
    else status = session ? "authenticated" : "anonymous";
    return {
      status,
      me: status === "disabled" ? LOCAL_ME : me,
      email: status === "disabled" ? LOCAL_ME.email : (session?.user.email ?? null),
      profileError, sessionExpired: expired,
      async signIn(email, password) {
        if (!supabase) throw new Error("Sign-in isn't set up.");
        const { error } = await supabase.auth.signInWithPassword({ email, password });
        if (error) throw new Error(authMessage(error));
        setExpired(false);
      },
      async signUp(email, password, requestedRole) {
        if (!supabase) throw new Error("Sign-in isn't set up.");
        const { data, error } = await supabase.auth.signUp({ email, password, options: { data: { requested_role: requestedRole }, emailRedirectTo: `${window.location.origin}/auth/login` } });
        if (error) throw new Error(authMessage(error));
        return { needsConfirmation: !data.session };
      },
      async signOut() { if (supabase) await supabase.auth.signOut(); setMe(null); },
      async requestPasswordReset(email) {
        if (!supabase) throw new Error("Sign-in isn't set up.");
        const { error } = await supabase.auth.resetPasswordForEmail(email, { redirectTo: `${window.location.origin}/auth/login` });
        if (error) throw new Error(authMessage(error));
      },
      async refreshProfile() { await loadProfile(sessionRef.current); },
      clearExpired() { setExpired(false); },
    };
  }, [supabase, ready, session, me, profileError, expired, loadProfile]);

  return <Ctx.Provider value={value}>{children}</Ctx.Provider>;
}
