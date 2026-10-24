import type { ReactNode } from "react";

// Inline SVG icons, 24px grid, 1.75 stroke. Decorative by default (aria-hidden); pass `label` when the icon stands alone.
const PATHS: Record<string, ReactNode> = {
  leaf: <path d="M5 19c0-8 5-13 14-14 0 9-5 14-13 14M5 19c2-4 5-7 9-9" />,
  pause: <><path d="M9 5v14" /><path d="M15 5v14" /></>,
  play: <path d="M8 5l11 7-11 7z" />,
  list: <><path d="M5 7h14M5 12h14M5 17h9" /></>,
  gauge: <><path d="M4 16a8 8 0 1116 0" /><path d="M12 16l4-5" /></>,
  photo: <><rect x="3" y="6" width="18" height="13" rx="2" /><circle cx="12" cy="12.5" r="3.2" /><path d="M8 6l1.2-2h5.6L16 6" /></>,
  satellite: <><circle cx="12" cy="12" r="3" /><path d="M3.5 15.5c-1.5-3 2.5-8.5 8.500-11.500M20.500 8.500c1.500 3-2.500 8.500-8.500 11.500" transform="rotate(20 12 12)" /></>,
  chat: <path d="M4 5h16v11H9l-5 4z" />,
  scale: <><path d="M12 4v16M6 20h12M5 7h14" /><path d="M5 7l-3 7a3 3 0 006 0zM19 7l-3 7a3 3 0 006 0z" /></>,
  person: <><circle cx="12" cy="8" r="3.5" /><path d="M5 20c1-4 4-6 7-6s6 2 7 6" /></>,
  check: <path d="M5 12.5l4.5 4.5L19 7" />,
  x: <path d="M6 6l12 12M18 6L6 18" />,
  alert: <><path d="M12 4l9 16H3z" /><path d="M12 10v4M12 17.5v.5" /></>,
  wifi: <><path d="M3 9a14 14 0 0118 0M6 12.5a9.5 9.5 0 0112 0M9 16a5 5 0 016 0" /><circle cx="12" cy="19" r="1" /></>,
  map: <><path d="M9 4L3 6v14l6-2 6 2 6-2V4l-6 2z" /><path d="M9 4v14M15 6v14" /></>,
  eye: <><path d="M2 12s3.5-7 10-7 10 7 10 7-3.5 7-10 7S2 12 2 12z" /><circle cx="12" cy="12" r="3" /></>,
  "eye-off": <><path d="M3 3l18 18" /><path d="M10.6 6.2A9.7 9.7 0 0112 6c6.5 0 10 6 10 6a17 17 0 01-3.2 3.9M6.6 7.6A17 17 0 002 12s3.5 6 10 6c1.5 0 2.8-.3 4-.8" /><path d="M9.9 9.9a3 3 0 004.2 4.2" /></>,
  file: <><path d="M7 3h7l4 4v14H7z" /><path d="M14 3v4h4M10 12h5M10 16h5" /></>,
};

export type IconName = keyof typeof PATHS;

export default function Icon({ name, size = 20, label }: { name: IconName; size?: number; label?: string }) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.75" strokeLinecap="round" strokeLinejoin="round"
      role={label ? "img" : undefined} aria-label={label} aria-hidden={label ? undefined : true} focusable="false">
      {PATHS[name]}
    </svg>
  );
}
