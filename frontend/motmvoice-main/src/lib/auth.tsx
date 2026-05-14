import { createContext, useContext, useEffect, useState, ReactNode } from "react";
import { authApi, type UserOut, type RegisterRequest } from "@/lib/api";

interface AuthCtx {
  user: UserOut | null;
  login: (email: string, password: string) => Promise<void>;
  register: (data: RegisterRequest) => Promise<void>;
  logout: () => void;
}

const Ctx = createContext<AuthCtx>({
  user: null,
  login: async () => {},
  register: async () => {},
  logout: () => {},
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

  function logout() {
    localStorage.removeItem("motm_token");
    localStorage.removeItem("motm_user");
    setUser(null);
  }

  return <Ctx.Provider value={{ user, login, register, logout }}>{children}</Ctx.Provider>;
}

export const useAuth = () => useContext(Ctx);
