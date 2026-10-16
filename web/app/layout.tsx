import type { Metadata, Viewport } from "next";
import { Inter, Inter_Tight, JetBrains_Mono } from "next/font/google";
import { OwnerAnalytics } from "../components/OwnerAnalytics";
import { Track } from "../components/Track";
import { SITE } from "../lib/site";
import "./globals.css";

const inter = Inter({ subsets: ["latin"], variable: "--font-inter", display: "swap" });
const interTight = Inter_Tight({ subsets: ["latin"], variable: "--font-display", display: "swap" });
const mono = JetBrains_Mono({ subsets: ["latin"], variable: "--font-mono", display: "swap" });

export const metadata: Metadata = {
  ...(SITE.url ? { metadataBase: new URL(SITE.url) } : {}),
  title: SITE.title,
  description: SITE.description,
  applicationName: "Deal Intelligence Agent",
  openGraph: {
    type: "website",
    siteName: "Deal Intelligence Agent",
    title: SITE.title,
    description: SITE.description,
    ...(SITE.url ? { url: SITE.url } : {}),
  },
  twitter: {
    card: "summary_large_image",
    title: SITE.title,
    description: SITE.description,
  },
};

export const viewport: Viewport = {
  themeColor: "#07080a",
  colorScheme: "dark",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" className={`${inter.variable} ${interTight.variable} ${mono.variable}`}>
      <body className="font-sans min-h-screen">
        {children}
        <OwnerAnalytics />
        <Track />
      </body>
    </html>
  );
}
