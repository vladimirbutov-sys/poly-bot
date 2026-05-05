import type { Metadata } from "next";
import { Geist_Mono } from "next/font/google";
import "./globals.css";
import Link from "next/link";

const mono = Geist_Mono({ subsets: ["latin"] });

export const metadata: Metadata = {
  title: "98_sure_bot",
  description: "Automated high-probability trading on Polymarket",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body className={`${mono.className} bg-zinc-950 text-zinc-100 min-h-screen`}>
        <nav className="border-b border-zinc-800 px-6 py-3 flex items-center gap-8">
          <span className="text-green-400 font-bold tracking-widest text-sm">
            98_SURE_BOT
          </span>
          <div className="flex gap-6 text-sm">
            <Link href="/" className="text-zinc-400 hover:text-white transition-colors">
              Overview
            </Link>
            <Link href="/bots" className="text-zinc-400 hover:text-white transition-colors">
              Позиции
            </Link>
            <Link href="/report" className="text-yellow-500 hover:text-yellow-300 transition-colors font-medium">
              Аналитика
            </Link>
          </div>
          <div className="ml-auto flex items-center gap-2">
            <span className="inline-block w-2 h-2 rounded-full bg-green-400 animate-pulse" />
            <span className="text-zinc-500 text-xs">LIVE</span>
          </div>
        </nav>
        <main className="max-w-7xl mx-auto px-6 py-8">{children}</main>
      </body>
    </html>
  );
}
