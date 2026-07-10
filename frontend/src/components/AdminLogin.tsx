import { useState } from "react";
import { KeyRound, LogIn } from "lucide-react";
import { AuthRequestError } from "../auth";

type AdminLoginProps = {
  onLogin: (adminToken: string) => Promise<void>;
  initialError?: string | null;
};

export function AdminLogin({ onLogin, initialError = null }: AdminLoginProps) {
  const [adminToken, setAdminToken] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(initialError);

  async function submit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!adminToken || submitting) return;
    setSubmitting(true);
    setError(null);
    try {
      await onLogin(adminToken);
    } catch (failure) {
      setError(
        failure instanceof AuthRequestError && failure.status === 401
          ? "管理员凭据无效，请检查后重试。"
          : "认证服务暂时不可用，请稍后重试。",
      );
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <main className="admin-login-shell">
      <section className="admin-login-panel" aria-labelledby="admin-login-title">
        <header className="admin-login-brand">
          <img src="/logo.png" alt="皇城司 HCS" />
          <div>
            <strong>皇城司 HCS</strong>
            <span>安全操作台</span>
          </div>
        </header>

        <div className="admin-login-heading">
          <KeyRound size={18} aria-hidden="true" />
          <div>
            <h1 id="admin-login-title">管理员登录</h1>
            <p>验证访问凭据后进入情报任务控制台。</p>
          </div>
        </div>

        <form onSubmit={submit} aria-busy={submitting}>
          <label htmlFor="admin-token">访问凭据</label>
          <input
            id="admin-token"
            name="admin-token"
            type="password"
            value={adminToken}
            onChange={(event) => setAdminToken(event.target.value)}
            autoComplete="current-password"
            autoFocus
            required
            disabled={submitting}
          />
          {error ? <p className="admin-login-error" role="alert">{error}</p> : null}
          <button type="submit" disabled={submitting || !adminToken}>
            <LogIn size={16} aria-hidden="true" />
            {submitting ? "正在验证" : "登录"}
          </button>
        </form>
      </section>
    </main>
  );
}
