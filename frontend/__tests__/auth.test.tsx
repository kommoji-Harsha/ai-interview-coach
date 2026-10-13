import React from "react";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, it, expect, vi, beforeEach } from "vitest";
import LoginPage from "@/app/auth/login/page";
import RegisterPage from "@/app/auth/register/page";
import { AuthProvider } from "@/lib/auth-context";
import * as api from "@/lib/api";

const pushMock = vi.fn();

vi.mock("next/navigation", () => ({
  useRouter: () => ({
    push: pushMock,
  }),
  usePathname: () => "/auth/login",
}));

describe("Auth Flow (Login & Register)", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    window.localStorage.clear();
  });

  it("validates login inputs and shows accessible error alerts", async () => {
    const user = userEvent.setup();
    render(
      <AuthProvider>
        <LoginPage />
      </AuthProvider>
    );

    const submitBtn = screen.getByRole("button", { name: /sign in/i });
    await user.click(submitBtn);

    expect(
      await screen.findByText(/please enter a valid email address/i)
    ).toBeInTheDocument();
    expect(
      screen.getByText(/password must be at least 8 characters/i)
    ).toBeInTheDocument();
  });

  it("submits login credentials and redirects to /onboarding", async () => {
    const user = userEvent.setup();
    vi.spyOn(api, "loginUser").mockResolvedValueOnce({
      user_id: "user-123",
      access_token: "token-abc",
      refresh_token: "refresh-abc",
      expires_at: "2026-12-31T00:00:00Z",
    });

    render(
      <AuthProvider>
        <LoginPage />
      </AuthProvider>
    );

    await user.type(screen.getByLabelText(/email address/i), "jane@example.com");
    await user.type(screen.getByLabelText(/password/i), "secret123!");
    await user.click(screen.getByRole("button", { name: /sign in/i }));

    await waitFor(() => {
      expect(api.loginUser).toHaveBeenCalledWith({
        email: "jane@example.com",
        password: "secret123!",
      });
      expect(pushMock).toHaveBeenCalledWith("/onboarding");
    });
  });

  it("displays API error state when login fails", async () => {
    const user = userEvent.setup();
    vi.spyOn(api, "loginUser").mockRejectedValueOnce(
      new api.ApiClientError("Invalid email or password", 401, "UNAUTHORIZED")
    );

    render(
      <AuthProvider>
        <LoginPage />
      </AuthProvider>
    );

    await user.type(screen.getByLabelText(/email address/i), "jane@example.com");
    await user.type(screen.getByLabelText(/password/i), "wrongpass!");
    await user.click(screen.getByRole("button", { name: /sign in/i }));

    expect(
      await screen.findByText(/invalid email or password/i)
    ).toBeInTheDocument();
  });

  it("registers a new user and redirects to /onboarding", async () => {
    const user = userEvent.setup();
    vi.spyOn(api, "registerUser").mockResolvedValueOnce({
      user_id: "user-456",
      email: "new@example.com",
      display_name: "Jane Doe",
      access_token: "token-xyz",
      refresh_token: "refresh-xyz",
      expires_at: "2026-12-31T00:00:00Z",
    });

    render(
      <AuthProvider>
        <RegisterPage />
      </AuthProvider>
    );

    await user.type(screen.getByLabelText(/display name/i), "Jane Doe");
    await user.type(screen.getByLabelText(/email address/i), "new@example.com");
    await user.type(screen.getByLabelText(/password/i), "strongpass!");
    await user.click(screen.getByRole("button", { name: /create account/i }));

    await waitFor(() => {
      expect(api.registerUser).toHaveBeenCalledWith({
        display_name: "Jane Doe",
        email: "new@example.com",
        password: "strongpass!",
      });
      expect(pushMock).toHaveBeenCalledWith("/onboarding");
    });
  });
});
