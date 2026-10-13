"use client";

import { useEffect } from "react";

/**
 * Page-wide behaviours, mounted once:
 *  - scroll reveal: marks `[data-reveal]` and `[data-grow]` with `data-inview`
 *    as they enter the viewport (content already on screen is marked before
 *    hiding is enabled, so nothing flickers; without JS nothing is hidden);
 *  - spotlight: feeds the cursor position to `.spotlight` cards as --mx/--my.
 */
export function Behaviours() {
  useEffect(() => {
    const root = document.body;
    const targets = Array.from(root.querySelectorAll<HTMLElement>("[data-reveal], [data-grow]"));
    const vh = window.innerHeight;
    for (const el of targets) {
      if (el.getBoundingClientRect().top < vh * 0.92) el.setAttribute("data-inview", "");
    }
    root.classList.add("reveal-ready");

    let io: IntersectionObserver | undefined;
    if ("IntersectionObserver" in window) {
      io = new IntersectionObserver(
        (entries) => {
          for (const entry of entries) {
            if (entry.isIntersecting) {
              entry.target.setAttribute("data-inview", "");
              io?.unobserve(entry.target);
            }
          }
        },
        { rootMargin: "0px 0px -8% 0px", threshold: 0.12 }
      );
      targets.filter((el) => !el.hasAttribute("data-inview")).forEach((el) => io?.observe(el));
    } else {
      targets.forEach((el) => el.setAttribute("data-inview", ""));
    }

    const onMove = (e: PointerEvent) => {
      const card = (e.target as HTMLElement | null)?.closest<HTMLElement>(".spotlight");
      if (!card) return;
      const r = card.getBoundingClientRect();
      card.style.setProperty("--mx", `${e.clientX - r.left}px`);
      card.style.setProperty("--my", `${e.clientY - r.top}px`);
    };
    root.addEventListener("pointermove", onMove, { passive: true });

    return () => {
      io?.disconnect();
      root.removeEventListener("pointermove", onMove);
    };
  }, []);
  return null;
}
