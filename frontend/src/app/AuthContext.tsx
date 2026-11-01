import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from "react";
import { ApiError, api, setCsrfToken } from "../services/api";
import type { AuthenticatedUser } from "../types/api";

interface AuthContextValue {
  user: AuthenticatedUser | null;
  loading: boolean;
  setupError: string | null;
  login: (username: string, password: string) => Promise<void>;
  logout: () => Promise<void>;
}

const AuthContext = createContext<AuthContextValue | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<AuthenticatedUser | null>(null);
  const [loading, setLoading] = useState(true);
  const [setupError, setSetupError] = useState<string | null>(null);

  const applyUser = useCallback((value: AuthenticatedUser | null) => {
    setUser(value);
    setCsrfToken(value?.csrf_token ?? null);
  }, []);

  useEffect(() => {
    let active = true;
    api<AuthenticatedUser>("/api/auth/session")
      .then((value) => {
        if (active) applyUser(value);
      })
      .catch((error: unknown) => {
        if (!active) return;
        if (error instanceof ApiError && error.status === 503) {
          setSetupError(error.message);
        }
        applyUser(null);
      })
      .finally(() => {
        if (active) setLoading(false);
      });
    return () => {
      active = false;
    };
  }, [applyUser]);

  const login = useCallback(
    async (username: string, password: string) => {
      const value = await api<AuthenticatedUser>("/api/auth/login", {
        method: "POST",
        body: JSON.stringify({ username, password }),
      });
      setSetupError(null);
      applyUser(value);
    },
    [applyUser],
  );

  const logout = useCallback(async () => {
    await api<void>("/api/auth/logout", { method: "POST" });
    applyUser(null);
  }, [applyUser]);

  const value = useMemo(
    () => ({ user, loading, setupError, login, logout }),
    [user, loading, setupError, login, logout],
  );
  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthContextValue {
  const value = useContext(AuthContext);
  if (!value) throw new Error("useAuth must be used within AuthProvider.");
  return value;
}
