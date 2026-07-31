import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from "react";
import { PLATFORM_ADMIN_KEY, PLATFORM_TOKEN_KEY, platformAuthApi, setPlatformUnauthorizedHandler } from "./platformApi";
import type { PlatformAdmin } from "./platformTypes";

interface PlatformAuthContextValue {
  admin: PlatformAdmin | null;
  isAuthenticated: boolean;
  isLoading: boolean;
  login: (email: string, password: string) => Promise<PlatformAdmin>;
  logout: () => void;
}

const PlatformAuthContext = createContext<PlatformAuthContextValue | undefined>(undefined);

function readStoredAdmin(): PlatformAdmin | null {
  try {
    const raw = localStorage.getItem(PLATFORM_ADMIN_KEY);
    return raw ? (JSON.parse(raw) as PlatformAdmin) : null;
  } catch {
    return null;
  }
}

/**
 * There is no `/api/platform/me` or refresh-token endpoint today (gap — flagged
 * for backend follow-up), so unlike the tenant AuthProvider this can't verify the
 * stored session on load. It trusts the `admin` snapshot saved at login time and
 * only clears it on an explicit logout or a 401 from any platform request.
 */
export function PlatformAuthProvider({ children }: { children: ReactNode }) {
  const [admin, setAdmin] = useState<PlatformAdmin | null>(() => readStoredAdmin());

  useEffect(() => {
    setPlatformUnauthorizedHandler(() => setAdmin(null));
    return () => setPlatformUnauthorizedHandler(() => {});
  }, []);

  const login = useCallback(async (email: string, password: string) => {
    const res = await platformAuthApi.login(email, password);
    localStorage.setItem(PLATFORM_TOKEN_KEY, res.data.access_token);
    localStorage.setItem(PLATFORM_ADMIN_KEY, JSON.stringify(res.data.admin));
    setAdmin(res.data.admin);
    return res.data.admin;
  }, []);

  // No server-side revoke endpoint exists yet for platform sessions (gap) —
  // this only clears local state, unlike the tenant logout which also hits the API.
  const logout = useCallback(() => {
    localStorage.removeItem(PLATFORM_TOKEN_KEY);
    localStorage.removeItem(PLATFORM_ADMIN_KEY);
    setAdmin(null);
  }, []);

  const value = useMemo<PlatformAuthContextValue>(
    () => ({ admin, isAuthenticated: !!admin, isLoading: false, login, logout }),
    [admin, login, logout]
  );

  return <PlatformAuthContext.Provider value={value}>{children}</PlatformAuthContext.Provider>;
}

export function usePlatformAuth() {
  const ctx = useContext(PlatformAuthContext);
  if (!ctx) throw new Error("usePlatformAuth must be used within PlatformAuthProvider");
  return ctx;
}
