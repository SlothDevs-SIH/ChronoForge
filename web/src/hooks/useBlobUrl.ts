import { useEffect, useState } from "react";
import { fetchBlobUrl } from "../lib/http";

/** Loads a protected image once and exposes it as an object URL; null while loading or if it is unavailable. */
export function useBlobUrl(url: string | null): { src: string | null; failed: boolean } {
  const [res, setRes] = useState<{ url: string | null; src: string | null; failed: boolean }>({ url: null, src: null, failed: false });
  useEffect(() => {
    if (!url) return;
    let made: string | null = null;
    let cancelled = false;
    fetchBlobUrl(url)
      .then((u) => { if (cancelled) URL.revokeObjectURL(u); else { made = u; setRes({ url, src: u, failed: false }); } })
      .catch(() => { if (!cancelled) setRes({ url, src: null, failed: true }); });
    return () => { cancelled = true; if (made) URL.revokeObjectURL(made); };
  }, [url]);
  // A result for a different url is stale: show the loading state until the new one arrives.
  return res.url === url ? { src: res.src, failed: res.failed } : { src: null, failed: false };
}
