"use client";
import { useState, useEffect } from "react";
import api from "@/lib/api";

interface AgentWeight { agent_id: number; agent_name: string; weight: number; }
interface FeedbackEntry {
  id: number; agent_id: number; error_type: string;
  predicted_delta: number; actual_delta: number; divergence_bps: number;
  negative_example_text: string; created_at: string;
}

export default function AdminPanel() {
  const [weights, setWeights] = useState<AgentWeight[]>([]);
  const [feedback, setFeedback] = useState<FeedbackEntry[]>([]);
  const [runStatus, setRunStatus] = useState("");
  const [tab, setTab] = useState<"weights" | "feedback" | "runs">("weights");

  useEffect(() => {
    api.get("/admin-secure-panel/api/weights").then(r => setWeights(r.data)).catch(() => {});
    api.get("/admin-secure-panel/api/feedback").then(r => setFeedback(r.data)).catch(() => {});
  }, []);

  async function updateWeight(agentId: number, weight: number) {
    await api.patch("/admin-secure-panel/api/weights", { agent_id: agentId, weight });
    setWeights(prev => prev.map(w => w.agent_id === agentId ? { ...w, weight } : w));
  }

  async function forceRun() {
    setRunStatus("Triggering…");
    await api.post("/admin-secure-panel/api/run");
    setRunStatus("Cycle triggered ✓");
    setTimeout(() => setRunStatus(""), 3000);
  }

  async function deleteFeedback(id: number) {
    await api.delete(`/admin-secure-panel/api/feedback/${id}`);
    setFeedback(prev => prev.filter(f => f.id !== id));
  }

  return (
    <main className="min-h-screen p-4 md:p-8 max-w-5xl mx-auto">
      <div className="flex items-center justify-between mb-8">
        <div>
          <h1 className="text-lg font-semibold">FED-WATCHER — ADMIN</h1>
          <p className="text-xs text-[var(--color-text-muted)]">Full system access</p>
        </div>
        <div className="flex items-center gap-3">
          <button
            onClick={forceRun}
            className="text-xs px-4 py-2 rounded font-medium transition-colors"
            style={{ background: "var(--color-gold)", color: "var(--color-navy)" }}
          >
            Force Run
          </button>
          {runStatus && <span className="text-xs text-[var(--color-signal-green)]">{runStatus}</span>}
          <a href="/" className="text-xs text-[var(--color-text-muted)] hover:text-[var(--color-text-primary)]">← Dashboard</a>
        </div>
      </div>

      {/* Tabs */}
      <div className="flex gap-1 mb-6">
        {(["weights", "feedback", "runs"] as const).map((t) => (
          <button
            key={t}
            onClick={() => setTab(t)}
            className="text-xs px-4 py-2 rounded transition-colors capitalize"
            style={{
              background: tab === t ? "var(--color-navy-700)" : "transparent",
              color: tab === t ? "var(--color-text-primary)" : "var(--color-text-muted)",
              border: `1px solid ${tab === t ? "var(--color-slate-400)" : "transparent"}`,
            }}
          >
            {t}
          </button>
        ))}
      </div>

      {/* Agent Weights */}
      {tab === "weights" && (
        <div className="card space-y-4">
          <p className="text-xs text-[var(--color-text-muted)] uppercase tracking-widest">Agent Weights (0.0 – 2.0)</p>
          {weights.map((w) => (
            <div key={w.agent_id} className="flex items-center gap-4">
              <span className="text-xs w-36 text-[var(--color-text-primary)]">{w.agent_name.replace("_", " ")}</span>
              <input
                type="range" min="0" max="2" step="0.1"
                value={w.weight}
                onChange={(e) => updateWeight(w.agent_id, parseFloat(e.target.value))}
                className="flex-1 accent-[var(--color-gold)]"
              />
              <span className="text-xs w-8 text-[var(--color-gold)]">{w.weight.toFixed(1)}</span>
            </div>
          ))}
        </div>
      )}

      {/* Feedback Log */}
      {tab === "feedback" && (
        <div className="card space-y-3">
          <p className="text-xs text-[var(--color-text-muted)] uppercase tracking-widest">
            Feedback Log — Negative Examples
          </p>
          {feedback.map((f) => (
            <div key={f.id} className="flex items-start gap-3 py-2 border-b border-[var(--color-navy-700)]">
              <div className="flex-1">
                <div className="flex items-center gap-2 mb-1">
                  <span className="text-xs text-[var(--color-gold)]">Agent {f.agent_id}</span>
                  <span className="text-xs text-[var(--color-text-muted)]">{f.error_type}</span>
                  <span className="text-xs text-[var(--color-signal-red)]">{f.divergence_bps.toFixed(0)} bps error</span>
                </div>
                <p className="text-xs text-[var(--color-text-muted)] leading-relaxed">{f.negative_example_text}</p>
              </div>
              <button
                onClick={() => deleteFeedback(f.id)}
                className="text-xs text-[var(--color-text-muted)] hover:text-[var(--color-signal-red)] shrink-0"
              >
                ✕
              </button>
            </div>
          ))}
          {feedback.length === 0 && (
            <p className="text-xs text-[var(--color-text-muted)]">No feedback entries yet.</p>
          )}
        </div>
      )}

      {/* Run History */}
      {tab === "runs" && <RunHistory />}
    </main>
  );
}

function RunHistory() {
  const [runs, setRuns] = useState<any[]>([]);
  useEffect(() => {
    api.get("/admin-secure-panel/api/runs").then(r => setRuns(r.data)).catch(() => {});
  }, []);

  return (
    <div className="card space-y-2">
      <p className="text-xs text-[var(--color-text-muted)] uppercase tracking-widest mb-3">Recent Runs</p>
      {runs.map((r) => (
        <div key={r.id} className="flex items-center gap-4 text-xs py-1.5 border-b border-[var(--color-navy-700)]">
          <span className="text-[var(--color-text-muted)] w-6">#{r.id}</span>
          <span className={r.status === "completed" ? "text-[var(--color-signal-green)]" : r.status === "failed" ? "text-[var(--color-signal-red)]" : "text-[var(--color-gold)]"}>
            {r.status}
          </span>
          <span className="text-[var(--color-text-muted)]">{r.cycle_type}</span>
          <span className="text-[var(--color-text-muted)] ml-auto">
            {r.started_at ? new Date(r.started_at).toLocaleString("ko-KR", { timeZone: "Asia/Seoul" }) : "—"}
          </span>
        </div>
      ))}
      {runs.length === 0 && <p className="text-xs text-[var(--color-text-muted)]">No runs yet.</p>}
    </div>
  );
}
