import { Component, type ReactNode } from "react";
import { Link } from "react-router-dom";

/** A render error in one page must never blank the whole app: show what happened and a way out. */
export default class ErrorBoundary extends Component<{ children: ReactNode; resetKey?: string }, { failed: boolean }> {
  state = { failed: false };
  static getDerivedStateFromError() { return { failed: true }; }
  componentDidCatch(error: unknown) { console.error("Page failed to render", error); }
  componentDidUpdate(prev: { resetKey?: string }) { if (this.state.failed && prev.resetKey !== this.props.resetKey) this.setState({ failed: false }); }
  render() {
    if (!this.state.failed) return this.props.children;
    return (
      <div className="error-state" role="alert">
        <div>
          <strong>This page hit a problem</strong>
          <p>Something on it couldn't be shown. Reloading usually fixes it. If it keeps happening, tell an administrator which page you were on.</p>
          <p><button type="button" className="btn btn-primary btn-sm" onClick={() => window.location.reload()}>Reload the page</button> <Link className="text-link" to="/">Go to the home page</Link></p>
        </div>
      </div>
    );
  }
}
