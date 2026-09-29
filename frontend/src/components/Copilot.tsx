"use client";

import { Bot, Send } from "lucide-react";
import { useState, type ReactNode } from "react";

import { post, type Brief } from "@/lib/api";
import { Card, StatusIcon } from "./ui";

function renderInline(s: string): ReactNode[] {
  return s.split(/(\*\*[^*]+\*\*)/g).map((part, i) =>
    part.startsWith("**") ? (
      <strong key={i} className="font-semibold text-ink">
        {part.slice(2, -2)}
      </strong>
    ) : (
      <span key={i}>{part}</span>
    ),
  );
}

export default function Copilot({ brief }: { brief?: Brief }) {
  const [q, setQ] = useState("");
  const [log, setLog] = useState<{ q: string; a: string }[]>([]);
  const [busy, setBusy] = useState(false);

  const ask = async (question: string) => {
    if (!question.trim()) return;
    setBusy(true);
    try {
      const r = await post<{ answer: string }>("/copilot/ask", { question });
      setLog((l) => [...l.slice(-3), { q: question, a: r.answer }]);
      setQ("");
    } catch (e) {
      setLog((l) => [...l, { q: question, a: (e as Error).message }]);
    } finally {
      setBusy(false);
    }
  };

  return (
    <Card className="flex h-full flex-col p-4">
      <div className="mb-3 flex items-center justify-between">
        <h2 className="flex items-center gap-2 text-sm font-semibold">
          <Bot size={16} className="text-accent" /> Trading copilot
        </h2>
        <span className="text-[11px] text-muted">{brief?.generated_by === "template" ? "deterministic brief" : brief?.generated_by}</span>
      </div>
      {!brief ? (
        <div className="h-40 animate-pulse rounded-lg bg-surface-2" />
      ) : (
        <>
          <div className="space-y-1.5 text-sm leading-relaxed text-ink-2">
            {brief.text.split("\n").map((l, i) => (
              <p key={i}>{renderInline(l)}</p>
            ))}
          </div>
          {brief.alerts.length > 0 && (
            <ul className="mt-4 space-y-2 border-t border-line pt-3">
              {brief.alerts.map((a) => (
                <li key={a.code} className="flex gap-2 text-xs text-ink-2">
                  <StatusIcon status={a.level} />
                  <span>{a.message}</span>
                </li>
              ))}
            </ul>
          )}
        </>
      )}
      <div className="mt-auto pt-4">
        {log.map((m, i) => (
          <div key={i} className="mb-2 text-xs">
            <div className="text-muted">› {m.q}</div>
            <div className="mt-0.5 text-ink">{m.a}</div>
          </div>
        ))}
        <div className="mb-2 flex flex-wrap gap-1.5">
          {["When do I charge?", "What is the risk?", "Why this price?"].map((s) => (
            <button key={s} onClick={() => ask(s)} className="rounded-full border border-line px-2 py-0.5 text-[11px] text-ink-2 hover:bg-surface-2">
              {s}
            </button>
          ))}
        </div>
        <form
          onSubmit={(e) => {
            e.preventDefault();
            ask(q);
          }}
          className="flex gap-2"
        >
          <input
            value={q}
            onChange={(e) => setQ(e.target.value)}
            placeholder="Ask about tomorrow's plan…"
            className="h-8 min-w-0 flex-1 rounded-md border border-line bg-surface-2 px-2.5 text-sm outline-none placeholder:text-muted focus:border-accent"
          />
          <button disabled={busy} className="grid size-8 place-items-center rounded-md bg-accent text-[#1a1a19] disabled:opacity-60" aria-label="Ask">
            <Send size={14} />
          </button>
        </form>
      </div>
    </Card>
  );
}
