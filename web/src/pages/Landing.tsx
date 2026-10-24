import { useRef, useState } from "react";
import { Link } from "react-router-dom";
import Icon from "../components/Icon";
import PublicNav from "../components/PublicNav";

const prefersReducedMotion = () => typeof window !== "undefined" && window.matchMedia("(prefers-reduced-motion: reduce)").matches;

export default function Landing() {
  const video = useRef<HTMLVideoElement>(null);
  // Reduced motion: show the still poster and let the person start playback.
  const [playing, setPlaying] = useState(() => !prefersReducedMotion());

  function toggle() {
    const el = video.current;
    if (!el) return;
    if (el.paused) { void el.play(); setPlaying(true); } else { el.pause(); setPlaying(false); }
  }

  return (
    <div className="hero-page">
      <video ref={video} className="hero-video" src="/assets/hero/hero.mp4" poster="/assets/hero/hero-poster.jpg"
        autoPlay={playing} muted loop playsInline preload="auto" aria-hidden="true" tabIndex={-1} />
      <div className="hero-veil" aria-hidden="true" />
      <PublicNav overlay />
      <main className="hero-main">
        <div className="hero-copy">
          <h1>Closed should mean <span className="hero-fixed">fixed.</span></h1>
          <p className="hero-lede">TrueClose checks whether a civic complaint marked resolved was actually repaired, using the closure photo, satellite imagery where it can see the problem, and the citizen who reported it.</p>
          <div className="hero-actions">
            <Link className="btn btn-primary" to="/how-it-works">See how it works</Link>
            <Link className="btn btn-secondary" to="/platform">Explore the platform</Link>
          </div>
          <p className="hero-note">A person approves every reopen. Satellite checks are skipped where they can't see the problem.</p>
        </div>
      </main>
      <div className="hero-caption">
        <span>Concept render. Not live data.</span>
        <button type="button" className="icon-btn" onClick={toggle} aria-label={playing ? "Pause background video" : "Play background video"}>
          <Icon name={playing ? "pause" : "play"} size={18} />
        </button>
      </div>
    </div>
  );
}
