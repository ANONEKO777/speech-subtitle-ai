import { type Locale, UNMANAGED_LOCALE } from "../i18n/locale";

const UNITS = ["B", "KB", "MB", "GB", "TB"] as const;

/** The decimal mark of `locale`. The digits are rounded with `toFixed`, so only the mark follows the language. */
const decimalMark = (locale: Locale): string => new Intl.NumberFormat(locale).formatToParts(1.1).find((p) => p.type === "decimal")?.value ?? ".";

export function bytes(n: number | null, locale: Locale = UNMANAGED_LOCALE): string {
  if (n === null) return "—";
  let value = Math.max(0, n);
  let unit = 0;
  while (value >= 1000 && unit < UNITS.length - 1) {
    value /= 1024;
    unit += 1;
  }
  const digits = unit === 0 || value >= 100 ? 0 : value >= 10 ? 1 : 2;
  return `${value.toFixed(digits).replace(".", decimalMark(locale))} ${UNITS[unit]}`;
}

export const mib = (n: number | null, locale: Locale = UNMANAGED_LOCALE): string => (n === null ? "—" : bytes(n * 1024 * 1024, locale));

export const speed = (bps: number, locale: Locale = UNMANAGED_LOCALE): string => (bps > 0 ? `${bytes(bps, locale)}/s` : "—");

/** A commit hash is too long for a table cell; a short version stays as it is. */
export const shortVersion = (v: string): string => (v.length > 12 ? `${v.slice(0, 8)}…` : v);
