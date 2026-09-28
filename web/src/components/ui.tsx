// Small building blocks for the war room: panels, badges, buttons, empty states.

import type { ButtonHTMLAttributes, ReactNode } from "react";

export function cx(...classes: (string | false | null | undefined)[]): string {
  return classes.filter(Boolean).join(" ");
}

export function Panel({
  title,
  actions,
  children,
  className,
  bodyClassName,
}: {
  title: ReactNode;
  actions?: ReactNode;
  children: ReactNode;
  className?: string;
  bodyClassName?: string;
}) {
  return (
    <section className={cx("flex min-h-0 flex-col rounded-md border border-border bg-panel", className)}>
      <header className="flex h-9 shrink-0 items-center justify-between gap-2 border-b border-border px-3">
        <h2 className="text-[11px] font-medium tracking-wider text-muted uppercase">{title}</h2>
        {actions}
      </header>
      <div className={cx("min-h-0 flex-1 p-3", bodyClassName)}>{children}</div>
    </section>
  );
}

export type Tone = "neutral" | "ok" | "warning" | "critical" | "memory";

const TONES: Record<Tone, string> = {
  neutral: "border-border text-muted",
  ok: "border-ok/40 text-ok",
  warning: "border-warning/40 text-warning",
  critical: "border-critical/50 text-critical",
  memory: "border-memory/50 bg-memory/10 text-memory",
};

export function Badge({ tone = "neutral", children, className }: { tone?: Tone; children: ReactNode; className?: string }) {
  return (
    <span
      className={cx(
        "inline-flex items-center gap-1 rounded border px-1.5 py-0.5 text-[11px] leading-none font-medium whitespace-nowrap",
        TONES[tone],
        className,
      )}
    >
      {children}
    </span>
  );
}

type Variant = "primary" | "ghost" | "memory" | "danger";

const VARIANTS: Record<Variant, string> = {
  primary: "bg-text text-bg hover:bg-text/90",
  ghost: "border border-border text-text hover:bg-border/60",
  memory: "bg-memory text-white hover:bg-memory/90",
  danger: "border border-critical/50 text-critical hover:bg-critical/10",
};

export function Button({
  variant = "ghost",
  className,
  ...props
}: ButtonHTMLAttributes<HTMLButtonElement> & { variant?: Variant }) {
  return (
    <button
      type="button"
      className={cx(
        "inline-flex h-8 items-center justify-center gap-1.5 rounded px-3 text-sm font-medium transition-colors disabled:pointer-events-none disabled:opacity-40",
        VARIANTS[variant],
        className,
      )}
      {...props}
    />
  );
}

export function Empty({ children }: { children: ReactNode }) {
  return <p className="py-6 text-center text-sm text-muted">{children}</p>;
}

export function Kbd({ children }: { children: ReactNode }) {
  return (
    <kbd className="rounded border border-border px-1 font-mono text-[10px] leading-4 text-muted">{children}</kbd>
  );
}

export function Select({
  label,
  value,
  onChange,
  options,
  className,
}: {
  label: string;
  value: string;
  onChange: (value: string) => void;
  options: { value: string; label: string }[];
  className?: string;
}) {
  return (
    <label className={cx("flex items-center gap-2 text-xs text-muted", className)}>
      {label}
      <select
        value={value}
        onChange={(e) => onChange(e.target.value)}
        className="h-8 rounded border border-border bg-bg px-2 text-sm text-text"
      >
        {options.map((o) => (
          <option key={o.value} value={o.value}>
            {o.label}
          </option>
        ))}
      </select>
    </label>
  );
}
