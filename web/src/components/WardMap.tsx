import { useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { api } from "../api";
import { usePeriod } from "../hooks/usePeriod";

type Mode = "official" | "reopen";
const RAMP = ["#dfe9dc", "#b4cdb0", "#79a58b", "#3f7a60", "#163d32"];   // one hue, light to dark
const W = 560;

const MODES: Record<Mode, { label: string; caption: string }> = {
  official: { label: "Official rate", caption: "Share of tickets no longer open, as the city reports it. Darker is higher." },
  reopen: { label: "After citizen reopens", caption: "Share of closed tickets the citizen later reopened. Darker is more reopened." },
};

/** Ward dots for one city, coloured in five quantile steps. A table below gives the same data to keyboard and screen-reader users. */
export default function WardMap({ city }: { city: string }) {
  const [mode, setMode] = useState<Mode>("official");
  const { days } = usePeriod();
  const { data, isPending, error } = useQuery({ queryKey: ["wardmap", city, days], queryFn: () => api.wardMap(city, days), retry: false });

  const view = useMemo(() => {
    const rows = (data ?? []).map((d) => ({ ...d, value: mode === "official" ? d.official_rate : d.reopen_rate }));
    const usable = rows.filter((r) => r.value != null);
    if (!rows.length) return null;
    const lat0 = rows.reduce((s, r) => s + r.lat, 0) / rows.length;
    const kx = Math.cos((lat0 * Math.PI) / 180);
    const xs = rows.map((r) => r.lng * kx), ys = rows.map((r) => -r.lat);
    const [x0, x1, y0, y1] = [Math.min(...xs), Math.max(...xs), Math.min(...ys), Math.max(...ys)];
    const scale = (W - 40) / Math.max(x1 - x0, 1e-6);
    const H = Math.min(520, Math.max(220, (y1 - y0) * scale + 40));
    const fit = Math.min(scale, (H - 40) / Math.max(y1 - y0, 1e-6));
    const sorted = usable.map((r) => r.value as number).sort((a, b) => a - b);
    const cut = [0.2, 0.4, 0.6, 0.8].map((q) => sorted[Math.floor(q * (sorted.length - 1))] ?? 0);
    const bin = (v: number) => cut.filter((c) => v > c).length;
    const maxT = Math.max(...rows.map((r) => r.tickets));
    return {
      H, cut, min: sorted[0], max: sorted[sorted.length - 1], usable: usable.length,
      dots: rows.map((r, i) => ({ ...r, cx: 20 + (xs[i] - x0) * fit, cy: 20 + (ys[i] - y0) * fit, r: 3 + 7 * Math.sqrt(r.tickets / maxT), fill: r.value == null ? "#ffffff" : RAMP[bin(r.value)] })),
    };
  }, [data, mode]);

  if (isPending) return <p className="muted">Loading ward positions…</p>;
  if (error) return <p className="muted">Ward positions are unavailable until the Engine responds.</p>;
  if (!view) return <p className="muted">This city has no ticket positions to map.</p>;
  const pctText = (v: number | null) => (v == null ? "n/a" : `${(v * 100).toFixed(v < 0.1 ? 1 : 0)}%`);
  const noReopens = mode === "reopen" && view.usable === 0;
  const top = [...view.dots].sort((a, b) => b.tickets - a.tickets).slice(0, 10);

  return (
    <div className="wardmap">
      <div className="seg" role="group" aria-label="Map measure">
        {(Object.keys(MODES) as Mode[]).map((m) => <button key={m} type="button" aria-pressed={mode === m} className={mode === m ? "is-on" : ""} onClick={() => setMode(m)}>{MODES[m].label}</button>)}
      </div>
      <p className="fine">{MODES[mode].caption} Dot size shows ticket volume.</p>
      {noReopens ? <p className="muted">This city's records carry no reopen status, so only the official rate can be shown.</p> : (
        <svg viewBox={`0 0 ${W} ${view.H}`} role="img" aria-label={`Map of ${view.dots.length} ${city} wards coloured by ${MODES[mode].label.toLowerCase()}. A table with the largest wards follows.`}>
          <rect width={W} height={view.H} rx="12" fill="#f1f4ee" />
          {view.dots.map((d) => <circle key={d.ward} cx={d.cx} cy={d.cy} r={d.r} fill={d.fill} stroke="#163d32" strokeOpacity={d.value == null ? 0.35 : 0.5} strokeWidth="0.8" fillOpacity="0.92"><title>{`${d.ward}: ${pctText(d.value)} (${d.tickets.toLocaleString()} tickets)`}</title></circle>)}
        </svg>
      )}
      {!noReopens && <div className="wardmap-legend" aria-hidden="true"><span>{pctText(view.min)}</span>{RAMP.map((c) => <i key={c} style={{ background: c }} />)}<span>{pctText(view.max)}</span></div>}
      <details className="bars-table"><summary>Show the largest wards as a table</summary>
        <table><thead><tr><th>Ward</th><th className="num">Tickets</th><th className="num">Official</th><th className="num">Reopened</th></tr></thead>
          <tbody>{top.map((d) => <tr key={d.ward}><td>{d.ward}</td><td className="num">{d.tickets.toLocaleString()}</td><td className="num">{pctText(d.official_rate)}</td><td className="num">{pctText(d.reopen_rate)}</td></tr>)}</tbody></table>
      </details>
      <p className="fine">Position is the mean of the ward's ticket locations. Bengaluru records give only a ward centre, so its dots show wards, not streets.</p>
    </div>
  );
}
