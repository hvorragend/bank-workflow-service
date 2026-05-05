import { clsx, type ClassValue } from "clsx";
import { twMerge } from "tailwind-merge";

/** Standard-shadcn-Helper: bedingte Klassen + Tailwind-Konflikt-Aufloesung. */
export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}

export function humanize(s: string | undefined | null): string {
  if (!s) return "";
  return s
    .replace(/([A-Z])/g, " $1")
    .replace(/_/g, " ")
    .replace(/^./, (c) => c.toUpperCase())
    .trim();
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
