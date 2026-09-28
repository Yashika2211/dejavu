// Numbers the way Kestrel Pay's engineers read them.

const LAKH = 100_000;
const CRORE = 10_000_000;

/** ₹28.5 lakh below one crore, ₹2.37 crore above (same rule as the backend). */
export function inr(amount: number): string {
  if (amount < 0) return `-${inr(-amount)}`;
  if (amount >= CRORE) return `₹${(amount / CRORE).toFixed(2)} crore`;
  return `₹${(amount / LAKH).toFixed(1)} lakh`;
}

/** Simulated minutes as a stopwatch: 07:30. */
export function stopwatch(minutes: number): string {
  const total = Math.max(0, Math.round(minutes * 60));
  const m = Math.floor(total / 60);
  const s = total % 60;
  return `${String(m).padStart(2, "0")}:${String(s).padStart(2, "0")}`;
}

export function minutes(value: number | null | undefined): string {
  if (value === null || value === undefined) return "n/a";
  return `${Number.isInteger(value) ? value : value.toFixed(1)} min`;
}

export function pct(value: number): string {
  return `${Math.round(value * 100)}%`;
}

/** Clock time in IST from an ISO timestamp plus simulated minutes. */
export function istTime(iso: string, plusMinutes = 0): string {
  const at = new Date(new Date(iso).getTime() + plusMinutes * 60_000);
  return at.toLocaleTimeString("en-IN", { hour: "2-digit", minute: "2-digit", hour12: false, timeZone: "Asia/Kolkata" });
}

export function istDate(iso: string): string {
  return new Date(iso).toLocaleDateString("en-IN", { day: "numeric", month: "short", timeZone: "Asia/Kolkata" });
}

export const humanize = (id: string) => id.replaceAll("_", " ");
