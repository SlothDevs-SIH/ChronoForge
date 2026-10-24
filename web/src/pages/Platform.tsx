import { useEffect, useRef, useState } from "react";
import { Link } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { api } from "../api";
import PublicNav, { PublicFooter } from "../components/PublicNav";
import { StatusDot } from "../components/ConnectionBadge";
import { EmptyState, ErrorState, Skeleton } from "../components/States";
import { useToast } from "../components/Toast";
import { useConnection } from "../hooks/useConnection";
import { ApiError, userMessage } from "../lib/http";
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
    </article>
  );
}

function DemoRun() {
  const toast = useToast();
  const { agent, agentStubs } = useConnection();
  const demo = useQuery({ queryKey: ["tickets", "demo"], queryFn: () => api.tickets("demo", undefined, 20), retry: false });
  const [selected, setSelected] = useState<string>("");
  const [events, setEvents] = useState<TraceEvent[]>([]);
  const [running, setRunning] = useState(false);
  const [runError, setRunError] = useState<string | null>(null);
  const close = useRef<(() => void) | undefined>();
  useEffect(() => () => close.current?.(), []);

  const ticketId = selected || demo.data?.[0]?.ticket.ticket_id || "";
  const verdict = [...events].reverse().find((e) => e.type === "verdict");
  const needsApproval = events.some((e) => e.type === "approval_needed");

  async function run() {
    setEvents([]); setRunError(null); setRunning(true);
    try {
      const { run_id } = await api.startRun(ticketId);
      close.current = api.streamRun(run_id, (e) => setEvents((prev) => [...prev, e]), (failed) => {
        setRunning(false);
        if (failed) setRunError("The live view was interrupted. The run may still have finished; open it from the dashboard.");
        else toast("success", `Verification finished for ${ticketId}.`);
      });
    } catch (e) {
      setRunning(false);
      setRunError(e instanceof ApiError && e.kind === "unauthorized" ? "Sign in to run a verification." : userMessage(e));
    }
  }

  if (demo.isPending) return <Skeleton rows={4} label="Loading demo tickets" />;
  if (demo.error && demo.error instanceof ApiError && demo.error.kind === "unauthorized") return <EmptyState title="Sign in to run a demo verification">The demo tickets are available to signed-in officers.</EmptyState>;
  if (demo.error) return <ErrorState error={demo.error} onRetry={() => void demo.refetch()} title="We couldn't load the demo tickets" />;
  if (!demo.data?.length) return <EmptyState title="No demo tickets are loaded">The demo set hasn't been loaded on this system yet.</EmptyState>;

  return (
    <div className="demo">
      <div className="demo-pick" role="radiogroup" aria-label="Demo ticket">
        {demo.data.map(({ ticket }) => (
          <button key={ticket.ticket_id} type="button" role="radio" aria-checked={ticket.ticket_id === ticketId} className={`chip ${ticket.ticket_id === ticketId ? "is-active" : ""}`}
            onClick={() => { setSelected(ticket.ticket_id); setEvents([]); setRunError(null); }}>{ticket.ticket_id}</button>
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
          {agent.state !== "connected" && <p className="fine">The verification agent is {agent.state === "connecting" ? "still connecting" : "not responding"}, so a run can't start yet.</p>}
          {agentStubs && <p className="fine">The agent is in stub mode: its tools return canned evidence, not real checks.</p>}
          {runError && <p className="field-error" role="alert">{runError}</p>}
          {events.length === 0 && !running && !runError && <p className="muted">Starts a real run. Each tool the agent chooses appears here as it happens.</p>}
          <ol className="trace-list" aria-live="polite">
            {events.map((e) => (
              <li key={`${e.run_id}-${e.step}`}><b>{e.tool ?? e.type.replace(/_/g, " ")}</b><span>{e.summary}</span><small>{e.budget_left} of 10 budget left</small></li>
            ))}
          </ol>
          {verdict && <div className="run-verdict"><strong>Verdict</strong><p>{verdict.summary}</p></div>}
          {needsApproval && <p className="fine">The agent recommends an action. Nothing happens until an officer decides in the approval queue.</p>}
        </div>
      </div>
      <p className="fine">Photo content is open-licence imagery from Wikimedia Commons (credits in the project's demo photo attribution file). Locations, times and the planted failures are synthetic demo data.</p>
    </div>
  );
}

export default function Platform() {
  const { engine, agent } = useConnection();
  const cities = useQuery({ queryKey: ["cities"], queryFn: api.cities, retry: false });
  const down = engine.state === "offline" || agent.state === "offline";

  return (
    <div className="pub-page">
      <PublicNav />
      <main className="pub-main">
        <header className="pub-head">
          <h1>System status</h1>
          <p>What is running behind TrueClose right now, the data it holds and a verification you can watch.</p>
        </header>

        <section className="panel" aria-labelledby="status-title">
          <div className="panel-head"><div><h2 id="status-title">Services</h2><p>Checked every five seconds.</p></div></div>
          <div className="status-grid">
            <div><StatusDot state={engine.state} name="Data service" /><p>{engine.detail}</p></div>
            <div><StatusDot state={agent.state} name="Verification agent" /><p>{agent.detail}</p></div>
          </div>
          {down && (
            <div className="offline" role="alert">
              <div>
                <strong>Part of the system isn't responding.</strong>
                <p>This page recovers by itself as soon as it is back. If it stays down, tell an administrator.</p>
              </div>
            </div>
          )}
        </section>

        <section className="panel" aria-labelledby="cities-title">
          <div className="panel-head"><div><h2 id="cities-title">The data it holds</h2><p>Synthetic cities are labelled and never mixed with real ones.</p></div></div>
          {cities.isPending && <Skeleton rows={3} label="Loading cities" />}
          {cities.error && <ErrorState error={cities.error} onRetry={() => void cities.refetch()} title="We couldn't load the city data" />}
          <div className="city-grid">{cities.data?.map((c) => <CityCard key={c.city} c={c} />)}</div>
        </section>

        <section className="panel" aria-labelledby="demo-title">
          <div className="panel-head"><div><h2 id="demo-title">Run a verification</h2><p>Twelve demo tickets with before and after photos, some with a planted failure. The agent decides which checks to spend its budget on.</p></div><span className="tag tag-simulated"><b>Simulated</b> demo tickets</span></div>
          <DemoRun />
        </section>
        <p className="fine">Officers can open the <Link className="text-link" to="/dashboard">dashboard</Link> to review real tickets.</p>
      </main>
      <PublicFooter current="/platform" />
    </div>
  );
}
