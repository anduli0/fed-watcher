"use client";
import { useState, FormEvent } from "react";
import { useRouter } from "next/navigation";
import api from "@/lib/api";

export default function LoginPage() {
  const router = useRouter();
  const [password, setPassword] = useState("");
  const [role, setRole] = useState<"deployment" | "admin">("deployment");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  async function handleSubmit(e: FormEvent) {
    e.preventDefault();
    setLoading(true);
    setError("");
    try {
      const res = await api.post("/auth/login", { password, role });
      if (res.data.role === "admin") {
        router.push("/admin-secure-panel");
      } else {
        router.push("/");
      }
    } catch {
      setError("Invalid credentials");
    } finally {
      setLoading(false);
    }
  }

  return (
    <main className="min-h-screen flex items-center justify-center p-4">
      <div className="card w-full max-w-sm space-y-6">
        <div>
          <h1 className="text-lg font-semibold">FED-WATCHER</h1>
          <p className="text-xs text-[var(--color-text-muted)] mt-1">Restricted Access</p>
        </div>
        <form onSubmit={handleSubmit} className="space-y-4">
          <div>
            <label className="text-xs text-[var(--color-text-muted)] block mb-1">Password</label>
            <input
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              className="w-full bg-[var(--color-navy-700)] border border-[var(--color-slate-400)] rounded px-3 py-2 text-sm text-[var(--color-text-primary)] focus:outline-none focus:border-[var(--color-gold)]"
              autoFocus
              required
            />
          </div>
          <div className="flex gap-2">
            {(["deployment", "admin"] as const).map((r) => (
              <button
                key={r}
                type="button"
                onClick={() => setRole(r)}
                className="flex-1 text-xs py-1.5 rounded border transition-colors"
                style={{
                  borderColor: role === r ? "var(--color-gold)" : "var(--color-navy-700)",
                  color: role === r ? "var(--color-gold)" : "var(--color-text-muted)",
                  background: role === r ? "var(--color-navy-700)" : "transparent",
                }}
              >
                {r}
              </button>
            ))}
          </div>
          {error && <p className="text-xs text-[var(--color-signal-red)]">{error}</p>}
          <button
            type="submit"
            disabled={loading}
            className="w-full py-2 rounded text-sm font-medium transition-colors"
            style={{
              background: "var(--color-gold)",
              color: "var(--color-navy)",
              opacity: loading ? 0.6 : 1,
            }}
          >
            {loading ? "…" : "Access"}
          </button>
        </form>
      </div>
    </main>
  );
}
