import { clsx, type ClassValue } from "clsx";
import { twMerge } from "tailwind-merge";

import type { FormInstance } from "@/types/api";

/** Standard-shadcn-Helper: bedingte Klassen + Tailwind-Konflikt-Aufloesung. */
export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}

/** Anzeigetitel eines Antrags — zentral, weil an mehreren Stellen benoetigt. */
export function instanceTitle(i: FormInstance): string {
  return i.daten?.vorhaben?.titel || i.daten?.beschluss?.titel || "(ohne Titel)";
}

/** Zahl im deutschen Format (Tausenderpunkte). */
export function formatNumber(n: number | null | undefined): string {
  if (n === null || n === undefined || Number.isNaN(n)) return "—";
  return n.toLocaleString("de-DE");
}

export function humanize(s: string | undefined | null): string {
  if (!s) return "";
  return s
    .replace(/([A-Z])/g, " $1")
    .replace(/_/g, " ")
    .replace(/^./, (c) => c.toUpperCase())
    .trim();
}

/**
 * Vergleicht zwei Versions-Strings semantisch (numerisch pro Segment), damit
 * z. B. "1.10.0" korrekt groesser als "1.9.0" ist (lexikographisch waere es
 * kleiner). Nicht-numerische Suffixe werden hinten angehaengt verglichen.
 * Rueckgabe: <0 wenn a<b, 0 bei Gleichheit, >0 wenn a>b.
 */
export function compareSemver(a: string, b: string): number {
  const norm = (v: string) =>
    v
      .replace(/^v/i, "")
      .split(/[.+-]/)
      .map((s) => (/^\d+$/.test(s) ? parseInt(s, 10) : s));
  const pa = norm(a);
  const pb = norm(b);
  const len = Math.max(pa.length, pb.length);
  for (let i = 0; i < len; i++) {
    const x = pa[i];
    const y = pb[i];
    if (x === undefined) return -1;
    if (y === undefined) return 1;
    if (typeof x === "number" && typeof y === "number") {
      if (x !== y) return x - y;
    } else {
      const xs = String(x);
      const ys = String(y);
      if (xs !== ys) return xs < ys ? -1 : 1;
    }
  }
  return 0;
}

export function formatDate(iso: string | null | undefined): string {
  if (!iso) return "";
  const d = new Date(iso);
  return (
    d.toLocaleDateString("de-DE") +
    " " +
    d.toLocaleTimeString("de-DE", { hour: "2-digit", minute: "2-digit" })
  );
}
