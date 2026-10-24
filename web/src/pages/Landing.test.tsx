import { describe, expect, it } from "vitest";
import { fireEvent, render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import Landing from "./Landing";

const setup = () => render(<MemoryRouter><Landing /></MemoryRouter>);

describe("Landing", () => {
  it("has one call to action and no top navigation links", () => {
    const { container } = setup();
    expect(screen.getByRole("link", { name: "Open the dashboard" })).toHaveAttribute("href", "/dashboard");
    expect(screen.queryByText(/Open the app|Explore the platform|See how it works/)).not.toBeInTheDocument();
    const header = container.querySelector("header")!;
    expect(header.querySelectorAll("a")).toHaveLength(1);     // only the brand, which goes home
  });

  it("reaches the other pages from footer links", () => {
    setup();
    const nav = screen.getByRole("navigation", { name: "More pages" });
    expect(nav).toHaveTextContent("How it works");
    expect(nav).toHaveTextContent("System status");
  });

  it("declares webm and mp4 sources, a poster and metadata preload", () => {
    const { container } = setup();
    const video = container.querySelector("video")!;
    expect(video).toHaveAttribute("poster", "/assets/hero/hero-poster.jpg");
    expect(video.getAttribute("preload")).toBe("metadata");
    expect(video.muted).toBe(true);
    expect([...container.querySelectorAll("source")].map((s) => s.getAttribute("type"))).toEqual(["video/webm", "video/mp4"]);
  });

  it("keeps the poster and drops the pause control when the video fails", () => {
    const { container } = setup();
    expect(screen.getByRole("button", { name: /pause background video/i })).toBeInTheDocument();
    fireEvent.error(container.querySelectorAll("source")[1]);
    expect(screen.queryByRole("button", { name: /background video/i })).not.toBeInTheDocument();
    expect(container.querySelector("video")).toHaveAttribute("poster");
  });

  it("labels the footage as a concept render", () => {
    setup();
    expect(screen.getByText("Concept render. Not live data.")).toBeInTheDocument();
  });
});
