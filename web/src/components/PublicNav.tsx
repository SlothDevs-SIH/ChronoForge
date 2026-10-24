import { Link, NavLink } from "react-router-dom";
import { homeFor, useAuth } from "../auth";
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
  const { user } = useAuth();
  return (
    <header className={`pub-nav ${overlay ? "pub-nav-overlay" : ""}`}>
      <div className="pub-nav-inner">
        <Brand />
        <nav aria-label="Primary">
          <NavLink to="/how-it-works">How it works</NavLink>
          <NavLink to="/platform">Platform</NavLink>
          <NavLink to="/evaluation">Evaluation</NavLink>
          {user
            ? <NavLink to={homeFor(user.role)} className="pub-nav-app">My workspace</NavLink>
            : <><NavLink to="/auth/login" className="pub-nav-signin">Sign in</NavLink><NavLink to="/auth/register" className="pub-nav-app">Get started</NavLink></>}
        </nav>
      </div>
    </header>
  );
}
