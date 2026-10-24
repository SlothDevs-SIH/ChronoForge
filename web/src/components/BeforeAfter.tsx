import { useId, useState } from "react";
import { useBlobUrl } from "../hooks/useBlobUrl";

/** Before/after comparison with a slider. Both images load through the authenticated client. */
export default function BeforeAfter({ beforeUrl, afterUrl, beforeAlt, afterAlt }: { beforeUrl: string; afterUrl: string; beforeAlt: string; afterAlt: string }) {
  const [pos, setPos] = useState(50);
  const id = useId();
  const before = useBlobUrl(beforeUrl);
  const after = useBlobUrl(afterUrl);
  if (before.failed || after.failed) return <p className="muted">The satellite images for this site aren't available.</p>;
  if (!before.src || !after.src) return <p className="muted">Loading satellite images…</p>;
  return (
    <div className="ba">
      <div className="ba-stage" style={{ ["--pos" as string]: `${pos}%` }}>
        <img src={after.src} alt={afterAlt} />
        <img className="ba-top" src={before.src} alt={beforeAlt} />
        <span className="ba-handle" aria-hidden="true" />
        <span className="ba-tag ba-tag-l">Before closure</span><span className="ba-tag ba-tag-r">After closure</span>
      </div>
      <label htmlFor={id} className="sr-only">Compare before and after closure</label>
      <input id={id} type="range" min={0} max={100} value={pos} onChange={(e) => setPos(Number(e.target.value))} />
    </div>
  );
}
