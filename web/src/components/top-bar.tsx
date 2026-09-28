"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

import { Badge, cx, Kbd } from "./ui";
import { HealthBanner, useHealth } from "./health";

const NAV = [
  { href: "/", label: "War Room" },
  { href: "/race", label: "Race" },
  { href: "/memory", label: "Memory" },
  { href: "/learning", label: "Learning" },
  { href: "/foresight", label: "Foresight" },
] as const;

export function TopBar() {
  const pathname = usePathname();
  const state = useHealth();
  const mode = state.health?.mode ?? "live";
  return (
    <>
      <header className="flex h-12 shrink-0 items-center gap-6 border-b border-border bg-panel px-4">
        <Link href="/" className="text-sm font-semibold tracking-tight whitespace-nowrap">
          Kestrel Pay <span className="text-muted">·</span> DejaVu
        </Link>
        <nav aria-label="Screens" className="flex items-center gap-1">
          {NAV.map((item) => {
            const active = item.href === "/" ? pathname === "/" : pathname.startsWith(item.href);
            return (
              <Link
                key={item.href}
                href={item.href}
                aria-current={active ? "page" : undefined}
                className={cx(
                  "rounded px-2.5 py-1.5 text-sm transition-colors",
                  active ? "bg-border text-text" : "text-muted hover:text-text",
                )}
              >
                {item.label}
              </Link>
            );
          })}
        </nav>
        <div className="ml-auto flex items-center gap-3">
          <span className="flex items-center gap-1.5 text-xs text-muted">
            Ask DejaVu <Kbd>⌘K</Kbd>
          </span>
          <Badge tone={mode === "live" ? "ok" : "warning"}>{mode === "live" ? "LIVE" : "REPLAY"}</Badge>
        </div>
      </header>
      <HealthBanner state={state} />
    </>
  );
}
