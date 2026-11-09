const UNITS = ["B", "KB", "MB", "GB", "TB"] as const;

export function bytes(n: number | null): string {
  if (n === null) return "—";
  let value = Math.max(0, n);
  let unit = 0;
  while (value >= 1000 && unit < UNITS.length - 1) {
    value /= 1024;
    unit += 1;
  }
  const digits = unit === 0 || value >= 100 ? 0 : value >= 10 ? 1 : 2;
  return `${value.toFixed(digits)} ${UNITS[unit]}`;
}

export const mib = (n: number | null): string => (n === null ? "—" : bytes(n * 1024 * 1024));

export const speed = (bps: number): string => (bps > 0 ? `${bytes(bps)}/s` : "—");

/** A commit hash is too long for a table cell; a short version stays as it is. */
export const shortVersion = (v: string): string => (v.length > 12 ? `${v.slice(0, 8)}…` : v);
