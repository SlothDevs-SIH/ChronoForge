import { createContext, useCallback, useContext, useRef, useState, type ReactNode } from "react";
import Icon from "./Icon";

type Tone = "success" | "error" | "info";
interface ToastItem { id: number; tone: Tone; text: string }

const ToastContext = createContext<(tone: Tone, text: string) => void>(() => undefined);
export const useToast = () => useContext(ToastContext);

// Toasts are only raised after a real API result (a decision recorded, a run finished, a request that failed).
export function ToastProvider({ children }: { children: ReactNode }) {
  const [items, setItems] = useState<ToastItem[]>([]);
  const next = useRef(0);
  const push = useCallback((tone: Tone, text: string) => {
    const id = ++next.current;
    setItems((prev) => [...prev.slice(-2), { id, tone, text }]);
    window.setTimeout(() => setItems((prev) => prev.filter((t) => t.id !== id)), tone === "error" ? 8000 : 5000);
  }, []);
  return (
    <ToastContext.Provider value={push}>
      {children}
      <div className="toast-region" role="status" aria-live="polite">
        {items.map((t) => (
          <div key={t.id} className={`toast toast-${t.tone}`}>
            <Icon name={t.tone === "error" ? "alert" : t.tone === "success" ? "check" : "list"} size={18} />
            <span>{t.text}</span>
            <button type="button" className="toast-close" aria-label="Dismiss" onClick={() => setItems((prev) => prev.filter((x) => x.id !== t.id))}><Icon name="x" size={16} /></button>
          </div>
        ))}
      </div>
    </ToastContext.Provider>
  );
}
