"use client";

import React, {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useState,
} from "react";
import {
  clearAuthTokens,
  getAccessToken,
  getStoredUser,
  loginUser,
  registerUser,
} from "./api";
import { LoginRequest, RegisterRequest } from "./types";

export interface AuthUser {
  user_id: string;
  email?: string;
  display_name?: string;
}

interface AuthContextValue {
  user: AuthUser | null;
  isAuthenticated: boolean;
  isLoading: boolean;
  login: (payload: LoginRequest) => Promise<void>;
  register: (payload: RegisterRequest) => Promise<void>;
  logout: () => void;
}

const AuthContext = createContext<AuthContextValue | undefined>(undefined);

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [user, setUser] = useState<AuthUser | null>(null);
  const [isLoading, setIsLoading] = useState<boolean>(true);

  useEffect(() => {
    const token = getAccessToken();
    const stored = getStoredUser();
    if (token && stored) {
      setUser(stored);
    } else if (token) {
      setUser({ user_id: "authenticated" });
    }
    setIsLoading(false);
  }, []);

  const login = useCallback(async (payload: LoginRequest) => {
    const res = await loginUser(payload);
    setUser({
      user_id: res.user_id,
      email: payload.email,
    });
  }, []);

  const register = useCallback(async (payload: RegisterRequest) => {
    const res = await registerUser(payload);
    setUser({
      user_id: res.user_id,
      email: res.email,
      display_name: res.display_name,
    });
  }, []);

  const logout = useCallback(() => {
    clearAuthTokens();
    setUser(null);
  }, []);

  return (
    <AuthContext.Provider
      value={{
        user,
        isAuthenticated: Boolean(user),
        isLoading,
        login,
        register,
        logout,
      }}
    >
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth(): AuthContextValue {
  const ctx = useContext(AuthContext);
  if (!ctx) {
    throw new Error("useAuth must be used within an AuthProvider");
  }
  return ctx;
}
