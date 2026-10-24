import type { ReactNode } from "react";
import { userMessage } from "../lib/http";
import Icon from "./Icon";

/** Placeholder rows while a list loads. */
export function Skeleton({ rows = 4, label = "Loading" }: { rows?: number; label?: string }) {
  return (
    <div className="skeleton" role="status" aria-label={label}>
      {Array.from({ length: rows }, (_, i) => <span key={i} className="skeleton-row" style={{ width: `${92 - (i % 3) * 14}%` }} />)}
    </div>
  );
}

/** What went wrong in plain words, with a retry. Never shows ports, paths or commands. */
export function ErrorState({ error, onRetry, title = "We couldn't load this" }: { error: unknown; onRetry?: () => void; title?: string }) {
  return (
    <div className="error-state" role="alert">
      <Icon name="alert" size={20} />
      <div>
        <strong>{title}</strong>
        <p>{userMessage(error)}</p>
        {onRetry && <button type="button" className="btn btn-secondary btn-sm" onClick={onRetry}>Try again</button>}
      </div>
    </div>
  );
}

export function EmptyState({ title, children }: { title: string; children?: ReactNode }) {
  return <div className="empty-state"><strong>{title}</strong>{children && <p>{children}</p>}</div>;
}
