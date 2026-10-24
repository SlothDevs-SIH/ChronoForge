import { Link } from "react-router-dom";
import Icon from "./Icon";

export function Brand({ light = false }: { light?: boolean }) {
  return (
    <Link className={`brand ${light ? "brand-light" : ""}`} to="/" aria-label="TrueClose home">
      <span className="brand-mark"><Icon name="leaf" size={20} /></span>
      <strong>TrueClose</strong>
    </Link>
  );
}

// The public pages carry only the brand at the top. Every other page is reached from the footer links, so no link
// points at the page it is on.
export default function PublicNav({ overlay = false }: { overlay?: boolean }) {
  return (
    <header className={`pub-nav ${overlay ? "pub-nav-overlay" : ""}`}>
      <div className="pub-nav-inner"><Brand /></div>
    </header>
  );
}

const LINKS = [
  { to: "/how-it-works", label: "How it works" },
  { to: "/evaluation", label: "Evaluation" },
  { to: "/platform", label: "System status" },
  { to: "/dashboard", label: "Dashboard" },
];

/** Footer links; the current page is shown as plain text, not a link. */
export function PublicFooterLinks({ current }: { current: string }) {
  return (
    <nav className="foot-links" aria-label="More pages">
      {LINKS.map((l) => l.to === current ? <span key={l.to} aria-current="page">{l.label}</span> : <Link key={l.to} to={l.to}>{l.label}</Link>)}
    </nav>
  );
}

export function PublicFooter({ current }: { current: string }) {
  return <footer className="pub-footer"><PublicFooterLinks current={current} /><small>Concept and demo data are labelled wherever they appear.</small></footer>;
}
