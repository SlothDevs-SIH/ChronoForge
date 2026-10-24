import { Children, type CSSProperties, type ReactNode } from "react";

/*
 * A card with a photo on top, a notched label at the photo's bottom-left and a pin at its top-right, in the style of the
 * Cutout Card from Cult UI. The reference uses shadcn, Tailwind and the `motion` library; this version is plain CSS (the
 * project decided against Tailwind) and the entrance is a CSS stagger that is switched off for prefers-reduced-motion.
 * The "cutout" is drawn with small radial-gradient corners that continue the label and pin colour into the photo.
 */

export function CutoutCard({ children, className = "" }: { children: ReactNode; className?: string }) {
  return <article className={`cutout ${className}`}>{children}</article>;
}

export function CutoutMedia({ children }: { children: ReactNode }) {
  return <div className="cutout-media">{children}</div>;
}

export function CutoutOverlay() {
  return <span className="cutout-overlay" aria-hidden="true" />;
}

/** The notched label at the bottom-left of the photo. */
export function CutoutLabel({ children }: { children: ReactNode }) {
  return <span className="cutout-label">{children}<i className="cutout-fillet cutout-fillet-up" aria-hidden="true" /><i className="cutout-fillet cutout-fillet-right" aria-hidden="true" /></span>;
}

/** The badge at the top-right of the photo. */
export function CutoutPin({ children, tone = "forest" }: { children: ReactNode; tone?: "forest" | "warning" | "danger" | "neutral" }) {
  return <span className={`cutout-pin cutout-pin-${tone}`}>{children}<i className="cutout-fillet cutout-fillet-left" aria-hidden="true" /><i className="cutout-fillet cutout-fillet-down" aria-hidden="true" /></span>;
}

/** Text area: its direct children enter one after another when the card first appears. */
export function CutoutContent({ children }: { children: ReactNode }) {
  return <div className="cutout-content">{Children.toArray(children).map((c, i) => <div key={i} className="cutout-step" style={{ "--i": i } as CSSProperties}>{c}</div>)}</div>;
}

export function CutoutFooter({ children }: { children: ReactNode }) {
  return <footer className="cutout-footer">{children}</footer>;
}

/** Real controls that sit at the bottom-right of the card. */
export function CutoutActions({ children }: { children: ReactNode }) {
  return <div className="cutout-actions">{children}</div>;
}
