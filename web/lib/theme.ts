// Shared by the server layout (boot script) and the client theme switch; must not be a client module.
export type Theme = "dark" | "light";
export const THEME_KEY = "di-theme";
export const THEME_COLOR: Record<Theme, string> = { dark: "#07080a", light: "#f7f6f2" };

/**
 * Runs in <head> before the first paint, so a reader who chose light never sees a dark flash.
 * Dark is the default; a stored choice wins. Kept tiny and dependency free on purpose.
 */
export const THEME_BOOT = `(function(){try{var t=localStorage.getItem("${THEME_KEY}");if(t==="light"){document.documentElement.dataset.theme="light";var m=document.querySelector('meta[name="theme-color"]');if(m)m.setAttribute("content","${THEME_COLOR.light}")}}catch(e){}})();`;

