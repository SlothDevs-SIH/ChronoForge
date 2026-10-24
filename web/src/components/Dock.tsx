import { useRef, type KeyboardEvent } from "react";
import Icon, { type IconName } from "./Icon";

export interface DockItem { id: string; label: string; icon: IconName; hint?: string }

const REACH = 130;     // px: how far from the pointer an item still grows
const MAX_GROW = 0.3; // extra scale of the icon tile at the pointer

const reducedMotion = () => typeof window !== "undefined" && window.matchMedia("(prefers-reduced-motion: reduce)").matches;

/**
 * A vertical dock in the style of the macOS Dock: items grow as the pointer (or keyboard focus) gets close.
 * Nothing moves until someone hovers, focuses or clicks. `selected` is the open step; `pressed` marks toggle items
 * (like "Try the evaluation") that open a panel without replacing the selected step. Items after `dividerBefore` sit
 * below a divider.
 */
export default function Dock({ label, items, selected, pressed = [], dividerBefore, onSelect }: {
  label: string; items: DockItem[]; selected: string; pressed?: string[]; dividerBefore?: string; onSelect: (id: string) => void;
}) {
  const refs = useRef<Record<string, HTMLButtonElement | null>>({});

  const grow = (centerY: number | null) => {
    for (const it of items) {
      const el = refs.current[it.id];
      if (!el) continue;
      let s = 1;
      if (centerY != null && !reducedMotion()) {
        const r = el.getBoundingClientRect();
        const d = Math.abs(r.top + r.height / 2 - centerY);
        s = 1 + MAX_GROW * Math.max(0, 1 - d / REACH) ** 2;
      }
      el.style.setProperty("--dock-scale", s.toFixed(3));
    }
  };

  const onKey = (e: KeyboardEvent, i: number) => {
    if (e.key !== "ArrowDown" && e.key !== "ArrowUp") return;
    e.preventDefault();
    const n = (i + (e.key === "ArrowDown" ? 1 : items.length - 1)) % items.length;
    refs.current[items[n].id]?.focus();
  };

  return (
    <div className="dock" role="toolbar" aria-orientation="vertical" aria-label={label}
      onPointerMove={(e) => grow(e.clientY)} onPointerLeave={() => grow(null)}>
      {items.map((it, i) => (
        <div key={it.id} className="dock-slot">
          {it.id === dividerBefore && <hr className="dock-divider" />}
          <button ref={(el) => { refs.current[it.id] = el; }} type="button" id={`dock-${it.id}`}
            className={`dock-item ${selected === it.id ? "is-selected" : ""} ${pressed.includes(it.id) ? "is-pressed" : ""}`}
            aria-pressed={pressed.includes(it.id) ? true : undefined}
            aria-current={selected === it.id ? "step" : undefined}
            onClick={() => onSelect(it.id)} onKeyDown={(e) => onKey(e, i)}
            onFocus={(e) => { const r = e.currentTarget.getBoundingClientRect(); grow(r.top + r.height / 2); }} onBlur={() => grow(null)}>
            <span className="dock-tile"><Icon name={it.icon} size={22} /></span>
            <span className="dock-text"><span className="dock-label">{it.label}</span>{it.hint && <span className="dock-hint">{it.hint}</span>}</span>
          </button>
        </div>
      ))}
    </div>
  );
}
