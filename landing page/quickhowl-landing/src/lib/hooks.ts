import { useEffect } from "react";
import { useQuery } from "@tanstack/react-query";
import { plansApi } from "@/lib/api";

export function usePublicPlans() {
  return useQuery({ queryKey: ["public-plans"], queryFn: () => plansApi.list().then((r) => r.data) });
}

// Drives the `.reveal-on-scroll` sections (see landing.css) with a one-time
// IntersectionObserver fade-in instead of the CSS-only `animation-timeline:
// view()` from styles.css — that's Chromium-only and scrubs to scroll
// position rather than playing a clean, consistent entrance everywhere.
export function useScrollReveal() {
  useEffect(() => {
    const targets = document.querySelectorAll<HTMLElement>(".reveal-on-scroll");
    const prefersReducedMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;

    if (prefersReducedMotion || typeof IntersectionObserver === "undefined") {
      targets.forEach((el) => el.classList.add("is-visible"));
      return;
    }

    const observer = new IntersectionObserver(
      (entries) => {
        for (const entry of entries) {
          if (entry.isIntersecting) {
            entry.target.classList.add("is-visible");
            observer.unobserve(entry.target);
          }
        }
      },
      { threshold: 0.15, rootMargin: "0px 0px -10% 0px" }
    );
    targets.forEach((el) => observer.observe(el));
    return () => observer.disconnect();
  }, []);
}
