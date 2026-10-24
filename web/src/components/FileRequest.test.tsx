import { describe, expect, it, vi, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import FileRequest from "./FileRequest";
import { ToastProvider } from "./Toast";

const refresh = vi.hoisted(() => vi.fn());
vi.mock("../auth/AuthProvider", () => ({ useAuth: () => ({ refreshProfile: refresh }) }));
const api = vi.hoisted(() => ({ similar: vi.fn(), submitRequest: vi.fn(), telegramLink: vi.fn() }));
vi.mock("../api", () => ({ api }));

function renderIt() {
  return render(
    <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
      <ToastProvider><FileRequest /></ToastProvider>
    </QueryClientProvider>,
  );
}

describe("FileRequest", () => {
  beforeEach(() => { vi.clearAllMocks(); api.similar.mockResolvedValue([]); });

  it("keeps Submit disabled until the problem is described", async () => {
    renderIt();
    const submit = screen.getByRole("button", { name: /submit request/i });
    expect(submit).toBeDisabled();
    await userEvent.type(screen.getByLabelText(/describe it/i), "Deep pothole at the gate");
    expect(submit).toBeEnabled();
  });

  it("files the request, refreshes the profile and offers the Telegram link", async () => {
    api.submitRequest.mockResolvedValue({ ticket: { ticket_id: "web-00007" }, telegram_link: "https://t.me/TruClosebot?start=abc", linked: false });
    renderIt();
    await userEvent.type(screen.getByLabelText(/describe it/i), "Deep pothole at the gate");
    await userEvent.type(screen.getByLabelText(/area or ward/i), "Kothrud");
    await userEvent.click(screen.getByRole("button", { name: /submit request/i }));
    expect(await screen.findByText(/web-00007 submitted/i)).toBeInTheDocument();
    expect(api.submitRequest).toHaveBeenCalledWith({ category: "pothole", text: "Deep pothole at the gate", ward: "Kothrud" });
    expect(refresh).toHaveBeenCalled();
    expect(screen.getByRole("link", { name: /connect telegram/i })).toHaveAttribute("href", "https://t.me/TruClosebot?start=abc");
  });

  it("warns about a similar open request without showing anyone's wording", async () => {
    api.similar.mockResolvedValue([{ ward: "Kothrud", status: "open", similarity: 0.6, created_at: "t" }]);
    renderIt();
    await userEvent.type(screen.getByLabelText(/describe it/i), "Deep pothole outside the school gate");
    await userEvent.type(screen.getByLabelText(/area or ward/i), "Kothrud");
    expect(await screen.findByText(/this may already be reported/i, {}, { timeout: 3000 })).toBeInTheDocument();
    expect(screen.getByText(/similar problem/i)).toHaveTextContent("Kothrud");
    expect(api.similar).toHaveBeenCalledWith("pothole", "Deep pothole outside the school gate", "Kothrud");
  });

  it("does not look for duplicates before a ward is given", async () => {
    renderIt();
    await userEvent.type(screen.getByLabelText(/describe it/i), "Deep pothole outside the school gate");
    await new Promise((r) => setTimeout(r, 900));
    expect(api.similar).not.toHaveBeenCalled();
  });

  it("says so when filing fails and stays on the form", async () => {
    api.submitRequest.mockRejectedValue(new Error("boom"));
    renderIt();
    await userEvent.type(screen.getByLabelText(/describe it/i), "Deep pothole at the gate");
    await userEvent.click(screen.getByRole("button", { name: /submit request/i }));
    await waitFor(() => expect(screen.getByRole("button", { name: /submit request/i })).toBeEnabled());
    expect(screen.queryByText(/submitted/i)).not.toBeInTheDocument();
  });
});
