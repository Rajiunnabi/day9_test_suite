import type { Metadata } from "next";
import { NavBar } from "@/components/NavBar";
import "./globals.css";

export const metadata: Metadata = {
  title: "Team Directory",
  description: "Day 11 — Next.js connected to a real FastAPI backend",
};

// The root layout. It renders once and stays mounted while people navigate
// between pages — that's the whole point of a layout vs a page: `children`
// swaps out underneath it, but <NavBar /> itself never remounts, so it
// never re-fetches or re-animates on every click.
export default function RootLayout({ children }: LayoutProps<"/">) {
  return (
    <html lang="en" className="h-full antialiased">
      <body className="min-h-full flex flex-col bg-slate-50 text-slate-900">
        <NavBar />
        <main className="mx-auto w-full max-w-5xl flex-1 px-6 py-8">
          {children}
        </main>
        <footer className="border-t border-slate-200 py-4 text-center text-xs text-slate-400">
            Day 11 — connected to the real FastAPI backend.
        </footer>
      </body>
    </html>
  );
}
