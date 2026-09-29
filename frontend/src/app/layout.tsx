import type { Metadata, Viewport } from "next";
import { GeistMono } from "geist/font/mono";
import { GeistSans } from "geist/font/sans";
import type { ReactNode } from "react";

import Shell from "@/components/shell/Shell";
import "./globals.css";
import Providers from "./providers";

export const metadata: Metadata = {
  title: "GridAlpha — AI battery trading copilot",
  description:
    "Probabilistic day-ahead power price forecasting and risk-aware battery dispatch for the German market.",
};

export const viewport: Viewport = { width: "device-width", initialScale: 1 };

// Applies the saved theme before paint (no flash). Falls back to the OS setting.
const themeScript = `try{var t=localStorage.getItem('ga-theme');if(t==='light'||t==='dark'){document.documentElement.setAttribute('data-theme',t)}}catch(e){}`;

export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    <html lang="en" className={`${GeistSans.variable} ${GeistMono.variable}`} suppressHydrationWarning>
      <head>
        <script dangerouslySetInnerHTML={{ __html: themeScript }} />
      </head>
      <body>
        <Providers>
          <Shell>{children}</Shell>
        </Providers>
      </body>
    </html>
  );
}
