import { createContext, useContext, useEffect, useState, ReactNode } from "react";
import { authApi, type UserOut, type RegisterRequest } from "@/lib/api";

interface AuthCtx {
  user: UserOut | null;
  isAdmin: boolean;
  login: (email: string, password: string) => Promise<void>;
  register: (data: RegisterRequest) => Promise<void>;
  logout: () => void;
  refreshUser: () => Promise<void>;
}

const Ctx = createContext<AuthCtx>({
  user: null,
  isAdmin: false,
  login: async () => {},
  register: async () => {},
  logout: () => {},
  refreshUser: async () => {},
});

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<UserOut | null>(null);

  useEffect(() => {
    if (typeof window === "undefined") return;
    const raw = localStorage.getItem("motm_user");
    if (raw) setUser(JSON.parse(raw));
  }, []);

  async function login(email: string, password: string) {
    const { data } = await authApi.login(email, password);
    localStorage.setItem("motm_token", data.access_token);
    localStorage.setItem("motm_user", JSON.stringify(data.user));
    setUser(data.user);
  }

  async function register(data: RegisterRequest) {
    const { data: resp } = await authApi.register(data);
    localStorage.setItem("motm_token", resp.access_token);
    localStorage.setItem("motm_user", JSON.stringify(resp.user));
    setUser(resp.user);
  }

  async function refreshUser() {
    try {
      const { data } = await authApi.me();
      localStorage.setItem("motm_user", JSON.stringify(data));
      setUser(data);
    } catch {
      // token expired — leave state as-is, route guard will redirect
    }
  }

  function logout() {
    localStorage.removeItem("motm_token");
    localStorage.removeItem("motm_user");
    setUser(null);
  }

  const isAdmin = user?.role === "admin";

  return (
    <Ctx.Provider value={{ user, isAdmin, login, register, logout, refreshUser }}>
      {children}
    </Ctx.Provider>
  );
}

export const useAuth = () => useContext(Ctx);
