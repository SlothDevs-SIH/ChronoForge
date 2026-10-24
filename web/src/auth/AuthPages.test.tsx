import { beforeEach, describe, expect, it, vi } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { ForgotPassword, Login, Pending, Register } from "./AuthPages";

const auth = vi.hoisted(() => ({ value: {} as Record<string, unknown> }));
vi.mock("./AuthProvider", () => ({ useAuth: () => auth.value }));

const wrap = (ui: React.ReactElement, path = "/auth/login") => render(<MemoryRouter initialEntries={[path]}>{ui}</MemoryRouter>);

beforeEach(() => {
  auth.value = {
    status: "anonymous", me: null, sessionExpired: false, clearExpired: vi.fn(),
    signIn: vi.fn().mockResolvedValue(undefined), signUp: vi.fn().mockResolvedValue({ needsConfirmation: true }),
    requestPasswordReset: vi.fn().mockResolvedValue(undefined), refreshProfile: vi.fn().mockResolvedValue(undefined), signOut: vi.fn(),
  };
});

describe("Login", () => {
  it("labels every field and offers no social buttons", () => {
    wrap(<Login />);
    expect(screen.getByLabelText("Email")).toBeRequired();
    expect(screen.getByLabelText("Password")).toBeRequired();
    expect(screen.queryByText(/google|github/i)).not.toBeInTheDocument();
  });

  it("shows the service's message next to the password field when sign-in fails", async () => {
    (auth.value.signIn as ReturnType<typeof vi.fn>).mockRejectedValue(new Error("That email and password don't match. Check them and try again."));
    wrap(<Login />);
    await userEvent.type(screen.getByLabelText("Email"), "a@b.co");
    await userEvent.type(screen.getByLabelText("Password"), "wrong-password");
    await userEvent.click(screen.getByRole("button", { name: "Sign in" }));
    expect(await screen.findByRole("alert")).toHaveTextContent(/don't match/);
    expect(screen.getByLabelText("Password")).toHaveAccessibleDescription(/don't match/);
  });

  it("toggles the password between hidden and visible with an accessible control", async () => {
    wrap(<Login />);
    const pw = screen.getByLabelText("Password");
    expect(pw).toHaveAttribute("type", "password");
    await userEvent.click(screen.getByRole("button", { name: "Show password" }));
    expect(pw).toHaveAttribute("type", "text");
  });

  it("tells the person when their session ended", () => {
    wrap(<Login />, "/auth/login?expired=1&next=%2Fapprovals");
    expect(screen.getByRole("status")).toHaveTextContent(/session ended/i);
  });

  it("the official sign-in has no sign-up link", () => {
    wrap(<Login mode="official" />, "/auth/official");
    expect(screen.getByRole("heading", { name: "Official sign-in" })).toBeInTheDocument();
    expect(screen.queryByRole("link", { name: /create an account/i })).not.toBeInTheDocument();
  });

  it("disables the form when sign-in is not set up", () => {
    auth.value = { ...auth.value, status: "unconfigured" };
    wrap(<Login />);
    expect(screen.getByRole("button", { name: "Sign in" })).toBeDisabled();
  });
});

describe("Register", () => {
  it("asks for an officer account only when the box is ticked, and says an administrator must approve", async () => {
    wrap(<Register />, "/auth/register");
    await userEvent.type(screen.getByLabelText("Email"), "o@city.gov");
    await userEvent.type(screen.getByLabelText(/Password/), "long-enough-pass");
    await userEvent.click(screen.getByRole("checkbox", { name: /municipal officer/i }));
    await userEvent.click(screen.getByRole("button", { name: "Create account" }));
    await waitFor(() => expect(auth.value.signUp).toHaveBeenCalledWith("o@city.gov", "long-enough-pass", "officer"));
    expect(await screen.findByText(/need approval from an administrator/i)).toBeInTheDocument();
  });

  it("registers a citizen by default", async () => {
    wrap(<Register />, "/auth/register");
    await userEvent.type(screen.getByLabelText("Email"), "c@home.in");
    await userEvent.type(screen.getByLabelText(/Password/), "long-enough-pass");
    await userEvent.click(screen.getByRole("button", { name: "Create account" }));
    await waitFor(() => expect(auth.value.signUp).toHaveBeenCalledWith("c@home.in", "long-enough-pass", "citizen"));
  });
});

describe("ForgotPassword and Pending", () => {
  it("says a link was sent without revealing whether the account exists", async () => {
    wrap(<ForgotPassword />, "/auth/forgot-password");
    await userEvent.type(screen.getByLabelText("Email"), "x@y.zz");
    await userEvent.click(screen.getByRole("button", { name: "Send reset link" }));
    expect(await screen.findByRole("status")).toHaveTextContent(/if an account exists/i);
  });

  it("the waiting screen offers a re-check and sign-out", async () => {
    auth.value = { ...auth.value, status: "authenticated", me: { role: "officer", status: "pending" } };
    wrap(<Pending />, "/auth/pending");
    await userEvent.click(screen.getByRole("button", { name: "Check again" }));
    expect(auth.value.refreshProfile).toHaveBeenCalled();
    expect(screen.getByRole("button", { name: "Sign out" })).toBeInTheDocument();
  });
});
