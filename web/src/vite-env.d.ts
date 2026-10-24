/// <reference types="vite/client" />

interface ImportMetaEnv {
  readonly VITE_ENGINE_URL?: string;
  readonly VITE_AGENT_URL?: string;
  readonly VITE_SUPABASE_URL?: string;
  readonly VITE_SUPABASE_ANON_KEY?: string;
  /** Written by the Vercel-Supabase integration; used when the VITE_ names are not set. */
  readonly NEXT_PUBLIC_SUPABASE_URL?: string;
  readonly NEXT_PUBLIC_SUPABASE_ANON_KEY?: string;
  /** "1" when the backends run with AUTH_REQUIRED=0 (local demo): skips sign-in. Never set in production. */
  readonly VITE_AUTH_DISABLED?: string;
}
interface ImportMeta { readonly env: ImportMetaEnv }
