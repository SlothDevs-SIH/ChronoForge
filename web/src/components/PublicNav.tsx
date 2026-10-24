import { Link, NavLink } from "react-router-dom";
import Icon from "./Icon";

export function Brand({ light = false }: { light?: boolean }) {
  return (
    <Link className={`brand ${light ? "brand-light" : ""}`} to="/" aria-label="TrueClose home">
      <span className="brand-mark"><Icon name="leaf" size={20} /></span>
      <strong>TrueClose</strong>
    </Link>
  );
}

export default function PublicNav({ overlay = false }: { overlay?: boolean }) {
  return (
    <header className={`pub-nav ${overlay ? "pub-nav-overlay" : ""}`}>
      <div className="pub-nav-inner">
        <Brand />
        <nav aria-label="Primary">
          <NavLink to="/how-it-works">How it works</NavLink>
          <NavLink to="/platform">Platform</NavLink>
          <NavLink to="/dashboard" className="pub-nav-app">Open the app</NavLink>
        </nav>
      </div>
    </header>
  );
}
