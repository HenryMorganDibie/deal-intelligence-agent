import type { ReactNode } from "react";
import { FloatingThemeToggle } from "../../components/FloatingThemeToggle";

export default function Layout({ children }: { children: ReactNode }) {
  return (
    <>
      <FloatingThemeToggle />
      {children}
    </>
  );
}
