import { FormEvent, useState } from "react";
import { Database, Eye, EyeOff, LockKeyhole, Orbit } from "lucide-react";
import { useAuth } from "../../app/AuthContext";
import { ApiError } from "../../services/api";
import { Button } from "../../components/ui/Primitives";

export function LoginPage({ configurationError }: { configurationError: string | null }) {
  const { login } = useAuth();
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [passwordVisible, setPasswordVisible] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError(null);
    setSubmitting(true);
    try {
      await login(username, password);
    } catch (reason) {
      setError(reason instanceof ApiError ? reason.message : "Sign in failed.");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <main className="login-page">
      <div className="login-aside">
        <div className="login-brand"><span className="brand-mark">O</span><strong>ORBIT</strong></div>
        <div className="login-aside-copy">
          <span className="eyebrow">DATA OPERATIONS PLATFORM</span>
          <h1>Clarity across every collection.</h1>
          <p>One secure workspace for your sources, records, and collection history.</p>
        </div>
        <div className="login-aside-footer"><Database size={16} /> Private administration workspace</div>
      </div>
      <div className="login-form-side">
        <form className="login-form" onSubmit={(event) => void submit(event)}>
          <div className="login-lock"><LockKeyhole size={21} /></div>
          <span className="eyebrow">ADMINISTRATOR ACCESS</span>
          <h2>Sign in to Orbit</h2>
          <p>Use your administrator account to continue.</p>
          {configurationError && (
            <div className="configuration-alert" role="alert">
              <strong>Administrator access is not configured</strong>
              <span>{configurationError} See the README setup instructions.</span>
            </div>
          )}
          {error && <div className="form-alert" role="alert">{error}</div>}
          <label>
            Username
            <input
              autoComplete="username"
              value={username}
              onChange={(event) => setUsername(event.target.value)}
              required
              disabled={Boolean(configurationError)}
            />
          </label>
          <label>
            Password
            <span className="password-input-wrap">
              <input
                id="admin-password"
                type={passwordVisible ? "text" : "password"}
                autoComplete="current-password"
                value={password}
                onChange={(event) => setPassword(event.target.value)}
                required
                disabled={Boolean(configurationError)}
              />
              <button
                className="password-visibility-toggle"
                type="button"
                aria-label={passwordVisible ? "Hide password" : "Show password"}
                aria-pressed={passwordVisible}
                aria-controls="admin-password"
                onClick={() => setPasswordVisible((visible) => !visible)}
              >
                {passwordVisible ? <EyeOff size={17} /> : <Eye size={17} />}
              </button>
            </span>
          </label>
          <Button type="submit" className="login-submit" disabled={submitting || Boolean(configurationError)}>
            {submitting ? "Signing in…" : "Sign in"}
          </Button>
          <span className="login-security"><Orbit size={14} /> Secure, server-managed administrator session</span>
        </form>
      </div>
    </main>
  );
}
