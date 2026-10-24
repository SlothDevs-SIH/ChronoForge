import { useQuery } from "@tanstack/react-query";
import { api } from "../api";

export default function Hotspots() {
  const { data, error, isLoading } = useQuery({ queryKey: ["hotspots"], queryFn: api.hotspots, retry: false });
  if (isLoading) return <div className="loading-state">Looking for repeat reopens…</div>;
  if (error) return <div className="error-state">Could not load the analysis. Check that the Engine is running. ({String(error)})</div>;
  const rows = data?.hotspots ?? [];
  return (
    <>
      <div className="page-heading"><div><h1>Repeat reopens</h1><p>Wards and closing officers whose closures are reopened far more often than the rest of their city.</p></div><span className="badge">{rows.length} flagged</span></div>
      {rows.length === 0 && <div className="empty-state"><strong>Nothing stands out.</strong><p>No ward or officer is reopened significantly more than their city average, or the cities loaded have no reopen data.</p></div>}
      {rows.length > 0 && (
        <section className="content-card"><div className="table-wrap"><table>
          <thead><tr><th>City</th><th>Type</th><th>Who</th><th className="num">Closed</th><th className="num">Reopened</th><th className="num">Rate</th><th className="num">City rate</th><th className="num">Times higher</th></tr></thead>
          <tbody>{rows.map((h) => (
            <tr key={`${h.city}-${h.kind}-${h.key}`}><td>{h.city}</td><td>{h.kind === "ward" ? "Ward" : "Closing officer"}</td><td>{h.kind === "closer" ? `officer ${h.key}` : h.key}</td>
              <td className="num">{h.closed}</td><td className="num">{h.reopened}</td><td className="num">{(h.rate * 100).toFixed(1)}%</td><td className="num">{(h.city_rate * 100).toFixed(1)}%</td><td className="num"><strong>{h.ratio}×</strong></td></tr>
          ))}</tbody></table></div></section>
      )}
      <p className="fine">{data?.rule}. {data?.caveat} Officers are shown only by an anonymous code.</p>
    </>
  );
}
