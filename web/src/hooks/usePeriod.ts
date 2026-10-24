import { useSearchParams } from "react-router-dom";

/**
 * The time window the staff pages share, kept in the address (`?period=90`) so a link keeps it. A window counts back from each
 * city's own latest ticket (the data ends on different dates), never from today.
 */
export const PERIODS = [
  { value: "", label: "All data", days: undefined },
  { value: "30", label: "Last month", days: 30 },
  { value: "90", label: "Last 3 months", days: 90 },
  { value: "180", label: "Last 6 months", days: 180 },
] as const;

export function usePeriod() {
  const [params, setParams] = useSearchParams();
  const raw = params.get("period") ?? "";
  const current = PERIODS.find((p) => p.value === raw) ?? PERIODS[0];
  function set(value: string) {
    setParams((prev) => {
      const next = new URLSearchParams(prev);
      if (value) next.set("period", value);
      else next.delete("period");
      return next;
    }, { replace: true });
  }
  return { days: current.days as number | undefined, value: current.value as string, label: current.label, set };
}
