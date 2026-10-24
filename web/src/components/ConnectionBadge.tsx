import { useConnection, type LinkState } from "../hooks/useConnection";

const LABEL: Record<LinkState, string> = { connecting: "Connecting", connected: "Connected", offline: "Offline", error: "Error" };

export function StatusDot({ state, name, detail }: { state: LinkState; name: string; detail?: string }) {
  return (
    <span className={`conn conn-${state}`} title={detail}>
      <i aria-hidden="true" />
      <span>{name}: {LABEL[state]}</span>
    </span>
  );
}

/** Compact Engine + Agent status for the app bar. */
export default function ConnectionBadge() {
  const { engine, agent } = useConnection();
  return (
    <div className="conn-group" role="status" aria-label="Backend connection status">
      <StatusDot state={engine.state} name="Engine" detail={engine.detail} />
      <StatusDot state={agent.state} name="Agent" detail={agent.detail} />
    </div>
  );
}
