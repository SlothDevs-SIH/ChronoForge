import { useRef, useState } from "react";
import { Link } from "react-router-dom";
import Icon from "../components/Icon";
import PublicNav, { PublicFooterLinks } from "../components/PublicNav";

// Reduced motion and data saver: show the poster and let the person start playback.
function stillOnly(): boolean {
  if (typeof window === "undefined") return false;
  const nav = navigator as Navigator & { connection?: { saveData?: boolean } };
  return window.matchMedia("(prefers-reduced-motion: reduce)").matches || Boolean(nav.connection?.saveData);
}

export default function Landing() {
  const video = useRef<HTMLVideoElement>(null);
  const [playing, setPlaying] = useState(() => !stillOnly());
  const [failed, setFailed] = useState(false);   // the video could not load: the poster stays as the background

  function toggle() {
    const el = video.current;
    if (!el) return;
    if (playing) { el.pause(); setPlaying(false); } else { void el.play(); setPlaying(true); }
  }

  return (
    <div className="hero-page">
      <video ref={video} className="hero-video" poster="/assets/hero/hero-poster.jpg" autoPlay={playing && !failed} muted loop playsInline
        preload="metadata" aria-hidden="true" tabIndex={-1} onError={() => setFailed(true)}>
        <source src="/assets/hero/hero.webm" type="video/webm" onError={() => undefined} />
        <source src="/assets/hero/hero.mp4" type="video/mp4" onError={() => setFailed(true)} />
      </video>
      <div className="hero-veil" aria-hidden="true" />
      <PublicNav overlay />
      <main className="hero-main">
        <div className="hero-copy">
          <h1>Closed should mean <span className="hero-fixed">fixed.</span></h1>
          <p className="hero-lede">TrueClose checks whether a civic complaint marked resolved was actually repaired, using the closure photo, satellite imagery where it can see the problem, and the citizen who reported it.</p>
          <div className="hero-actions">
            <Link className="btn btn-primary" to="/dashboard">Open the dashboard</Link>
          </div>
          <p className="hero-note">A person approves every reopen. Satellite checks are skipped where they can't see the problem.</p>
        </div>
      </main>
      <div className="hero-foot">
        <PublicFooterLinks current="/" />
        <div className="hero-caption">
          <span>Concept render. Not live data.</span>
          {!failed && (
            <button type="button" className="icon-btn" onClick={toggle} aria-label={playing ? "Pause background video" : "Play background video"}>
              <Icon name={playing ? "pause" : "play"} size={18} />
            </button>
          )}
        </div>
      </div>
    </div>
  );
}
