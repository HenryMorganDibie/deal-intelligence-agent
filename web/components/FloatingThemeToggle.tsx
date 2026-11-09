import { ThemeToggle } from "./ThemeToggle";

/** For pages without a site header (sign-in, account, admin, review): the theme switch in the corner. */
export function FloatingThemeToggle() {
  return (
    <div className="fixed right-4 top-4 z-50">
      <ThemeToggle className="bg-raised/80 backdrop-blur" />
    </div>
  );
}
