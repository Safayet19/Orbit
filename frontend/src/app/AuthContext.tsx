import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
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
  const authRequestId = useRef(0);
  const logoutRequest = useRef<Promise<void> | null>(null);

  const applyUser = useCallback((value: AuthenticatedUser | null) => {
    setUser(value);
    setCsrfToken(value?.csrf_token ?? null);
  }, []);

  useEffect(() => {
    let active = true;
    const requestId = ++authRequestId.current;
    const controller = new AbortController();
    api<AuthenticatedUser>("/api/auth/session", { signal: controller.signal })
      .then((value) => {
        if (active && requestId === authRequestId.current) applyUser(value);
      })
      .catch((error: unknown) => {
        if (!active || requestId !== authRequestId.current) return;
        if (error instanceof ApiError && error.status === 503) {
          setSetupError(error.message);
        }
        applyUser(null);
      })
      .finally(() => {
        if (active && requestId === authRequestId.current) setLoading(false);
      });
    return () => {
      active = false;
      controller.abort();
    };
  }, [applyUser]);

  const login = useCallback(
    async (username: string, password: string) => {
      const requestId = ++authRequestId.current;
      const value = await api<AuthenticatedUser>("/api/auth/login", {
        method: "POST",
        body: JSON.stringify({ username, password }),
      });
      if (requestId !== authRequestId.current) return;
      setSetupError(null);
      applyUser(value);
    },
    [applyUser],
  );

  const logout = useCallback(async () => {
    if (logoutRequest.current) return logoutRequest.current;
    const requestId = ++authRequestId.current;
    const request = api<void>("/api/auth/logout", { method: "POST" })
      .then(() => {
        if (requestId === authRequestId.current) applyUser(null);
      })
      .catch((error: unknown) => {
        if (
          error instanceof ApiError &&
          error.status === 401 &&
          requestId === authRequestId.current
        ) {
          applyUser(null);
        }
        throw error;
      });
    logoutRequest.current = request;
    try {
      await request;
    } finally {
      if (logoutRequest.current === request) logoutRequest.current = null;
    }
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
