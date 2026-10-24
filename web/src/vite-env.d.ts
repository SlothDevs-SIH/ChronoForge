/// <reference types="vite/client" />

interface ImportMetaEnv {
  readonly VITE_ENGINE_URL?: string;
  readonly VITE_AGENT_URL?: string;
  readonly VITE_SUPABASE_URL?: string;
  readonly VITE_SUPABASE_ANON_KEY?: string;
  /** "1" when the backends run with AUTH_REQUIRED=0 (local demo): skips sign-in. Never set in production. */
  readonly VITE_AUTH_DISABLED?: string;
}
interface ImportMeta { readonly env: ImportMetaEnv }
