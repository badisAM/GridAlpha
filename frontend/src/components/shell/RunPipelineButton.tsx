"use client";

import { useQueryClient } from "@tanstack/react-query";
import { Loader2, Play } from "lucide-react";
import { useEffect, useRef, useState } from "react";

import { get, post, type Health } from "@/lib/api";
import { useHealth } from "@/lib/hooks";

export default function RunPipelineButton() {
  const qc = useQueryClient();
  const { data } = useHealth();
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState<string | null>(null);
  const timer = useRef<ReturnType<typeof setInterval> | null>(null);
  const running = busy || !!data?.pipeline_running;

  useEffect(() => () => {
    if (timer.current) clearInterval(timer.current);
  }, []);

  const start = async () => {
    setMsg(null);
    try {
      setBusy(true);
      await post("/pipeline/run", { quick: true });
      timer.current = setInterval(async () => {
        const h = await get<Health>("/health");
        if (!h.pipeline_running) {
          if (timer.current) clearInterval(timer.current);
          setBusy(false);
          setMsg(h.last_run?.status === "success" ? "Pipeline finished" : "Pipeline failed — see Monitoring");
          qc.invalidateQueries();
        }
      }, 3000);
    } catch (e) {
      setBusy(false);
      setMsg((e as Error).message);
    }
  };

  return (
    <div className="flex items-center gap-2">
      {msg && <span className="hidden text-xs text-ink-2 sm:inline">{msg}</span>}
      <button
        onClick={start}
        disabled={running}
        className="inline-flex h-8 items-center gap-1.5 rounded-md border border-line bg-surface px-3 text-xs font-medium text-ink hover:bg-surface-2 disabled:opacity-60"
        title="Ingest → features → backtest (90 d) → train → forecast → optimise"
      >
        {running ? <Loader2 size={14} className="animate-spin" /> : <Play size={14} />}
        {running ? "Running pipeline…" : "Run pipeline"}
      </button>
    </div>
  );
}
