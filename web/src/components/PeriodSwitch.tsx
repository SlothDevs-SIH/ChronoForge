import { useQuery } from "@tanstack/react-query";
import { useSearchParams } from "react-router-dom";
import { api } from "../api";
import { PERIODS, usePeriod } from "../hooks/usePeriod";

const fmt = (iso?: string | null) => (iso ? new Date(iso).toLocaleDateString([], { day: "numeric", month: "short", year: "numeric" }) : "");
const title = (s: string) => s.charAt(0).toUpperCase() + s.slice(1);

/** Month and window buttons for the staff pages, with a plain statement of what the numbers cover. */
export default function PeriodSwitch({ onChange }: { onChange?: () => void }) {
  const period = usePeriod();
  const [params] = useSearchParams();
  const city = params.get("city") ?? "";
  const cities = useQuery({ queryKey: ["cities"], queryFn: () => api.cities(), retry: false, staleTime: 5 * 60_000 });
  const info = city ? cities.data?.find((c) => c.city === city) : undefined;

  let note: string;
  if (period.days) {
    note = info?.data_as_of
      ? `Tickets raised in the ${period.days} days before ${fmt(info.data_as_of)}, the latest ticket in ${title(city)}.`
      : `Tickets raised in the ${period.days} days before the latest ticket in each city. The data ends on different dates, so this is not counted from today.`;
  } else {
    note = info?.data_as_of ? `All loaded tickets for ${title(city)}: ${fmt(info.data_from)} to ${fmt(info.data_as_of)}.` : "All loaded tickets.";
  }
  return (
    <div className="period-switch">
      <div className="period-buttons" role="group" aria-label="Time period">
        {PERIODS.map((p) => (
          <button key={p.value || "all"} type="button" aria-pressed={period.value === p.value} className={period.value === p.value ? "is-on" : ""}
            onClick={() => { period.set(p.value); onChange?.(); }}>{p.label}</button>
        ))}
      </div>
      <p className="fine period-note">{note}</p>
    </div>
  );
}
