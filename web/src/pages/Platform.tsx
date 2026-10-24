import { useEffect, useRef, useState } from "react";
import { Link } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { api } from "../api";
import Icon from "../components/Icon";
import PublicNav from "../components/PublicNav";
import { StatusDot } from "../components/ConnectionBadge";
import { useToast } from "../components/Toast";
import { useConnection } from "../hooks/useConnection";
import type { CitySummary, TraceEvent } from "../types";

const QUALITY_TEXT: Record<CitySummary["data_quality"], string> = { real: "Real records", partial: "Partly real", synthetic: "Synthetic" };
const PRECISION_TEXT: Record<string, string> = { exact: "Exact location", generated: "Generated location", ward_centroid: "Ward centre only", none: "No location" };

function CityCard({ c }: { c: CitySummary }) {
  return (
    <article className="city-card">
      <header><h3>{c.city[0].toUpperCase() + c.city.slice(1)}</h3><span className={`tag tag-${c.data_quality === "synthetic" ? "simulated" : "real"}`}>{QUALITY_TEXT[c.data_quality]}</span></header>
      <p className="city-count">{c.tickets.toLocaleString()}<span> tickets</span></p>
      <dl>
        <div><dt>Closed</dt><dd>{c.closed.toLocaleString()}</dd></div>
        <div><dt>Reopened</dt><dd>{c.reopened.toLocaleString()}</dd></div>
        <div><dt>Open</dt><dd>{c.open.toLocaleString()}</dd></div>
        <div><dt>Location</dt><dd>{PRECISION_TEXT[c.location_precision ?? "none"]}</dd></div>
      </dl>
      <Link className="text-link" to={`/triage?city=${c.city}`}>Open the {c.city} queue</Link>
    </article>
  );
}

function DemoRun() {
  const toast = useToast();
  const { agent, agentStubs } = useConnection();
  const { data: demo, error, isPending } = useQuery({ queryKey: ["tickets", "demo"], queryFn: () => api.tickets("demo", undefined, 20), retry: false });
  const [selected, setSelected] = useState<string>("");
  const [events, setEvents] = useState<TraceEvent[]>([]);
  const [running, setRunning] = useState(false);
  const close = useRef<(() => void) | undefined>();
  useEffect(() => () => close.current?.(), []);

  const ticketId = selected || demo?.[0]?.ticket.ticket_id || "";
  const verdict = [...events].reverse().find((e) => e.type === "verdict");
  const needsApproval = events.some((e) => e.type === "approval_needed");

  async function run() {
    setEvents([]);
    setRunning(true);
    try {
      const { run_id } = await api.startRun(ticketId);
      close.current = api.streamRun(run_id, (e) => setEvents((prev) => [...prev, e]), () => { setRunning(false); toast("success", `Verification finished for ${ticketId}.`); });
    } catch {
      setRunning(false);
      toast("error", `The Agent could not start a run for ${ticketId}. Check that it is running on port 8002.`);
    }
  }

  if (isPending) return <p className="muted">Loading demo tickets…</p>;
  if (error || !demo?.length) return <p className="muted">No demo tickets are loaded. Run <code>python -m app.ingest demo</code> in the engine folder.</p>;

  return (
    <div className="demo">
      <div className="demo-pick" role="radiogroup" aria-label="Demo ticket">
        {demo.map(({ ticket }) => (
          <button key={ticket.ticket_id} type="button" role="radio" aria-checked={ticket.ticket_id === ticketId} className={`chip ${ticket.ticket_id === ticketId ? "is-active" : ""}`}
            onClick={() => { setSelected(ticket.ticket_id); setEvents([]); }}>{ticket.ticket_id}</button>
        ))}
      </div>
      <div className="demo-body">
        <div className="demo-photos">
          {(["before", "after"] as const).map((w) => (
            <figure key={w + ticketId}>
              <img src={api.demoPhoto(ticketId, w)} alt={w === "before" ? "Photo of the problem as reported" : "Photo attached when the ticket was closed"} loading="lazy" width={400} height={300} />
              <figcaption>{w === "before" ? "As reported" : "At closure"}</figcaption>
            </figure>
          ))}
        </div>
        <div className="demo-run">
          <button type="button" className="btn btn-primary" onClick={run} disabled={running || agent.state !== "connected"}>{running ? "Checking the evidence…" : "Run the verification agent"}</button>
          {agent.state !== "connected" && <p className="fine">The Agent is {agent.state === "connecting" ? "still connecting" : "not responding"}, so a run can't start.</p>}
          {agentStubs && <p className="fine">The Agent is in stub mode: tools return canned evidence, not real checks.</p>}
          {events.length === 0 && !running && <p className="muted">Starts a real run. Each tool the agent chooses appears here as it happens.</p>}
          <ol className="trace-list" aria-live="polite">
            {events.map((e) => (
              <li key={`${e.run_id}-${e.step}`}><b>{e.tool ?? e.type.replace(/_/g, " ")}</b><span>{e.summary}</span><small>{e.budget_left} of 10 budget left</small></li>
            ))}
          </ol>
          {verdict && <div className="run-verdict"><strong>Verdict</strong><p>{verdict.summary}</p></div>}
          {needsApproval && <p className="fine">The agent recommends an action. Nothing happens until someone decides in the <Link className="text-link" to="/approvals">approval queue</Link>.</p>}
        </div>
      </div>
      <p className="fine">Photo content is open-licence imagery from Wikimedia Commons (credits in demo/photos/ATTRIBUTION.md). Locations, times and the planted failures are synthetic demo data.</p>
    </div>
  );
}

export default function Platform() {
  const { engine, agent } = useConnection();
  const cities = useQuery({ queryKey: ["cities"], queryFn: api.cities, retry: false });
  const offline = engine.state === "offline" || agent.state === "offline";

  return (
    <div className="pub-page">
      <PublicNav />
      <main className="pub-main">
        <header className="pub-head">
          <h1>Explore the platform</h1>
          <p>What is running behind TrueClose right now, the data it holds and a verification you can run yourself.</p>
        </header>

        <section className="panel" aria-labelledby="status-title">
          <div className="panel-head"><div><h2 id="status-title">Connection status</h2><p>Checked every five seconds through the same proxy this page uses.</p></div></div>
          <div className="status-grid">
            <div><StatusDot state={engine.state} name="Engine (port 8001)" /><p>{engine.detail}</p></div>
            <div><StatusDot state={agent.state} name="Agent (port 8002)" /><p>{agent.detail}</p></div>
          </div>
          {offline && (
            <div className="offline" role="alert">
              <Icon name="alert" size={20} />
              <div>
                <strong>A backend is not responding.</strong>
                <p>Start it from the repository root, then this page recovers by itself.</p>
                <pre>{`cd engine && uvicorn app.main:app --port 8001
cd agent  && AGENT_USE_STUBS=0 uvicorn app.main:app --port 8002`}</pre>
              </div>
            </div>
          )}
        </section>

        <section className="panel" aria-labelledby="cities-title">
          <div className="panel-head"><div><h2 id="cities-title">The data it holds</h2><p>Counts come from the Engine. Synthetic cities are labelled and never mixed with real ones.</p></div></div>
          {cities.isPending && <p className="muted">Loading cities…</p>}
          {cities.isError && <p className="muted">Cities are unavailable until the Engine responds.</p>}
          <div className="city-grid">{cities.data?.map((c) => <CityCard key={c.city} c={c} />)}</div>
        </section>

        <section className="panel" aria-labelledby="demo-title">
          <div className="panel-head"><div><h2 id="demo-title">Run a verification</h2><p>Twelve demo tickets with before and after photos, some with a planted failure. The agent decides which checks to spend its budget on.</p></div><span className="tag tag-simulated"><b>Simulated</b> demo tickets</span></div>
          <DemoRun />
        </section>

        <div className="pub-cta">
          <p>Ready for the officer view?</p>
          <Link className="btn btn-primary" to="/dashboard">Open the app</Link>
          <Link className="btn btn-secondary" to="/how-it-works">See how it works</Link>
        </div>
      </main>
    </div>
  );
}
