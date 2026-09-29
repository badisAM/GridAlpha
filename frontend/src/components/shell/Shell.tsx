"use client";

import clsx from "clsx";
import {
  Activity,
  BarChart3,
  Battery,
  BrainCircuit,
  Briefcase,
  CandlestickChart,
  Gauge,
  Moon,
  Radio,
  SlidersHorizontal,
  Sun,
  Zap,
} from "lucide-react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useState, type ReactNode } from "react";

import { useHealth } from "@/lib/hooks";
import { ago } from "@/lib/format";
import RunPipelineButton from "./RunPipelineButton";

const NAV = [
  { href: "/", label: "Trading desk", icon: CandlestickChart },
  { href: "/market", label: "Market", icon: BarChart3 },
  { href: "/simulator", label: "Simulator", icon: SlidersHorizontal },
  { href: "/backtest", label: "Backtest", icon: Battery },
  { href: "/models", label: "Models", icon: BrainCircuit },
  { href: "/live", label: "Live replay", icon: Radio },
  { href: "/monitoring", label: "Monitoring", icon: Activity },
  { href: "/business", label: "Business case", icon: Briefcase },
];

function ThemeToggle() {
  const [theme, setTheme] = useState<"light" | "dark" | null>(null);
  useEffect(() => {
    const attr = document.documentElement.getAttribute("data-theme") as "light" | "dark" | null;
    const os = window.matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light";
    setTheme(attr ?? os);
  }, []);
  const flip = () => {
    const next = theme === "dark" ? "light" : "dark";
    document.documentElement.setAttribute("data-theme", next);
    try {
      localStorage.setItem("ga-theme", next);
    } catch {}
    setTheme(next);
  };
  return (
    <button
      onClick={flip}
      aria-label="Toggle colour theme"
      className="grid size-8 place-items-center rounded-md border border-line text-ink-2 hover:bg-surface-2 hover:text-ink"
    >
      {theme === "dark" ? <Sun size={15} /> : <Moon size={15} />}
    </button>
  );
}

function StatusStrip() {
  const { data } = useHealth();
  const live = data?.data_mode === "live";
  return (
    <div className="flex min-w-0 items-center gap-2 text-xs text-ink-2">
      {data?.data_mode && (
        <span
          className={clsx(
            "inline-flex items-center gap-1.5 rounded-full border px-2 py-0.5 font-medium",
            live ? "border-good/40 text-good-text" : "border-accent/40 text-accent",
          )}
          title={live ? "Energy-Charts + Open-Meteo + Yahoo (scraped)" : "Calibrated market simulator (APIs unreachable)"}
        >
          <span className={clsx("size-1.5 rounded-full", live ? "bg-good" : "bg-accent")} />
          {live ? "LIVE DATA" : "SIMULATED DATA"}
        </span>
      )}
      <span className="hidden truncate md:inline">
        model <span className="font-mono text-ink">{data?.model_version ?? "—"}</span>
      </span>
      <span className="hidden truncate lg:inline">· last run {ago(data?.last_run?.finished_at)}</span>
    </div>
  );
}

export default function Shell({ children }: { children: ReactNode }) {
  const path = usePathname();
  return (
    <div className="min-h-dvh lg:grid lg:grid-cols-[220px_1fr]">
      <aside className="z-20 border-b border-line bg-surface lg:sticky lg:top-0 lg:h-dvh lg:border-r lg:border-b-0">
        <div className="flex items-center gap-2 px-4 py-3 lg:py-5">
          <div className="grid size-8 place-items-center rounded-lg bg-accent text-[#1a1a19]">
            <Zap size={17} strokeWidth={2.5} />
          </div>
          <div className="leading-tight">
            <div className="text-sm font-semibold tracking-tight">GridAlpha</div>
            <div className="text-[11px] text-muted">Battery trading copilot</div>
          </div>
        </div>
        <nav className="flex gap-1 overflow-x-auto px-2 pb-2 lg:flex-col lg:overflow-visible lg:pb-0">
          {NAV.map(({ href, label, icon: Icon }) => {
            const active = href === "/" ? path === "/" : path.startsWith(href);
            return (
              <Link
                key={href}
                href={href}
                className={clsx(
                  "flex shrink-0 items-center gap-2.5 rounded-md px-3 py-2 text-sm transition-colors",
                  active ? "bg-accent-soft font-medium text-ink" : "text-ink-2 hover:bg-surface-2 hover:text-ink",
                )}
              >
                <Icon size={16} className={active ? "text-accent" : ""} />
                {label}
              </Link>
            );
          })}
        </nav>
        <div className="hidden px-4 pt-6 text-[11px] leading-relaxed text-muted lg:absolute lg:bottom-4 lg:block">
          <Gauge size={13} className="mb-1 inline" /> DE-LU day-ahead · gate closure 12:00 CET
          <br />
          Built by Ammar Bedis
        </div>
      </aside>
      <div className="min-w-0">
        <header className="sticky top-0 z-10 flex items-center justify-between gap-3 border-b border-line bg-page/85 px-4 py-2.5 backdrop-blur md:px-6">
          <StatusStrip />
          <div className="flex items-center gap-2">
            <RunPipelineButton />
            <ThemeToggle />
          </div>
        </header>
        <main className="mx-auto max-w-[1440px] px-4 py-5 md:px-6 md:py-6">{children}</main>
      </div>
    </div>
  );
}
