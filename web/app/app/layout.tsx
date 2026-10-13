import type { Metadata } from "next";
import { AppShell } from "../../components/app/AppShell";

export const metadata: Metadata = { title: "Briefs | Deal Intelligence", robots: { index: false } };

export default function AppLayout({ children }: { children: React.ReactNode }) {
  return <AppShell>{children}</AppShell>;
}
