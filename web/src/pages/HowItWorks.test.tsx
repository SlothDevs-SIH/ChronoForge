import { describe, expect, it } from "vitest";
import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { http, HttpResponse } from "msw";
import { server } from "../test/server";
import HowItWorks from "./HowItWorks";

function setup() {
  server.use(http.get("http://engine.test/cities", () => HttpResponse.json([{ city: "pune", tickets: 10, closed: 5, reopened: 1, open: 4, data_quality: "synthetic", location_precision: "generated" }])));
  return render(<QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}><MemoryRouter><HowItWorks /></MemoryRouter></QueryClientProvider>);
}

describe("How it works", () => {
  it("shows a first step and nothing animated or open until someone clicks", () => {
    setup();
    expect(screen.getByRole("heading", { name: "A complaint is marked resolved" })).toBeInTheDocument();
    expect(screen.queryByRole("heading", { name: "Try the evaluation" })).not.toBeInTheDocument();
  });

  it("opens a step when its dock item is clicked", async () => {
    setup();
    await userEvent.click(screen.getByRole("button", { name: /Risk assessment/ }));
    expect(screen.getByRole("heading", { name: "Risk assessment" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Risk assessment/ })).toHaveAttribute("aria-current", "step");
  });

  it("has six steps plus a seventh item that pops the evaluation open below the step", async () => {
    setup();
    const dock = screen.getByRole("toolbar", { name: "Verification steps" });
    expect(within(dock).getAllByRole("button")).toHaveLength(7);
    await userEvent.click(within(dock).getByRole("button", { name: /Try the evaluation/ }));
    expect(screen.getByRole("heading", { name: "Try the evaluation" })).toBeInTheDocument();
    // the step stays visible: the evaluation opens beside the dock, below the step detail
    expect(screen.getByRole("heading", { name: "A complaint is marked resolved" })).toBeInTheDocument();
    expect(within(dock).getByRole("button", { name: /Try the evaluation/ })).toHaveAttribute("aria-pressed", "true");
    await userEvent.click(screen.getByRole("button", { name: /Close the evaluation example/ }));
    expect(screen.queryByRole("heading", { name: "Try the evaluation" })).not.toBeInTheDocument();
  });

  it("moves between dock items with the arrow keys", async () => {
    setup();
    screen.getByRole("button", { name: /A complaint is marked resolved/ }).focus();
    await userEvent.keyboard("{ArrowDown}");
    expect(screen.getByRole("button", { name: /Risk assessment/ })).toHaveFocus();
  });

  it("does the odds arithmetic from the Agent's configured ratios", async () => {
    setup();
    await userEvent.click(screen.getByRole("button", { name: /Try the evaluation/ }));
    // prior 30%, photo clean x0.5, citizen no reply x1.2, satellite not checked x1 -> odds 0.4286 * 0.6 = 0.2571 -> 20%
    expect(screen.getByText("20%")).toBeInTheDocument();
    await userEvent.selectOptions(screen.getByLabelText("Closure photo"), "Photo is a duplicate");
    // 0.4286 * 8 * 1.2 = 4.114 -> 80%
    expect(screen.getByText("80%")).toBeInTheDocument();
    expect(screen.getByText("Likely not fixed")).toBeInTheDocument();
  });

  it("has no link to the page it is on and no call-to-action block", () => {
    setup();
    expect(screen.queryByRole("link", { name: "How it works" })).not.toBeInTheDocument();
    expect(screen.queryByText(/Explore the platform/)).not.toBeInTheDocument();
  });
});
