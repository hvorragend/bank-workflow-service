/**
 * JSON-Schema-Renderer-Helfer — wortgleich portiert aus dem Vue-Vorgaenger.
 *
 * Die UI-Schemas verwenden eine Untermenge der JSON-Forms-Konvention:
 *   - "scope": "#/properties/foo/properties/bar" zeigt auf einen Pfad im JSON-Schema
 *   - "rule":  { effect: "SHOW" | "HIDE", condition: { scope, schema: { const: X } } }
 *              steuert Conditional-Rendering
 */
import type { JsonSchema, UiControl } from "@/types/api";

/** Aufloesen einer Scope-Referenz im JSON-Schema-Baum. */
export function resolveScope(schema: JsonSchema, scope: string): JsonSchema | undefined {
  if (!schema || !scope) return undefined;
  const parts = scope.replace(/^#\//, "").split("/");
  let node: any = schema;
  for (const p of parts) {
    if (!node || typeof node !== "object") return undefined;
    node = node[p];
  }
  return node;
}

export function scopeKey(scope: string): string {
  return scope.split("/").pop() ?? "";
}

export function scopePath(scope: string): string[] {
  return scope.replace(/^#\//, "").split("/").filter((p) => p !== "properties");
}

export function isRequired(scope: string, schema: JsonSchema): boolean {
  const path = scopePath(scope);
  if (path.length === 0) return false;
  const fieldName = path[path.length - 1];
  const parentPath = path.slice(0, -1);
  let parent: any = schema;
  for (const k of parentPath) parent = parent?.properties?.[k];
  return Array.isArray(parent?.required) && parent.required.includes(fieldName);
}

export function getByPath(obj: any, path: string[]): any {
  return path.reduce((o, k) => (o == null ? o : o[k]), obj);
}

export function setByPath(obj: any, path: string[], value: any): void {
  let cur: any = obj;
  for (let i = 0; i < path.length - 1; i++) {
    const k = path[i];
    if (cur[k] == null || typeof cur[k] !== "object") cur[k] = {};
    cur = cur[k];
  }
  cur[path[path.length - 1]] = value;
}

/** Initialisiert ein leeres Datenobjekt aus dem Schema. Booleans bleiben undefined,
 *  damit der User aktiv Ja/Nein waehlen muss. */
export function initFormData(schema: JsonSchema | undefined): any {
  if (!schema) return {};
  if (schema.type === "object" && schema.properties) {
    const obj: any = {};
    for (const [k, v] of Object.entries(schema.properties)) {
      obj[k] = initFormData(v as JsonSchema);
    }
    return obj;
  }
  if (schema.type === "boolean") return undefined;
  return "";
}

/** Entfernt undefined und leere Strings rekursiv. So scheitern leere Pflichtfelder
 *  beim Backend mit "is a required property" statt "''" is too short". */
export function pruneEmpty(value: any): any {
  if (Array.isArray(value)) return value.map(pruneEmpty);
  if (value && typeof value === "object") {
    const out: Record<string, any> = {};
    for (const [k, v] of Object.entries(value)) {
      if (v === undefined || v === "") continue;
      const cleaned = v && typeof v === "object" ? pruneEmpty(v) : v;
      if (
        cleaned &&
        typeof cleaned === "object" &&
        !Array.isArray(cleaned) &&
        Object.keys(cleaned).length === 0
      )
        continue;
      out[k] = cleaned;
    }
    return out;
  }
  return value;
}

/** Sehr kleines JSON-Schema-Match fuer UI-Rules. Unterstuetzt const und enum. */
function matchSchema(schema: any, value: any): boolean {
  if (!schema) return true;
  if ("const" in schema) return value === schema.const;
  if ("enum" in schema) return Array.isArray(schema.enum) && schema.enum.includes(value);
  return true;
}

/** Auswertung einer UI-Rule (effect SHOW/HIDE/DISABLE). */
export function isVisible(ctrl: UiControl, data: any): boolean {
  if (!ctrl?.rule) return true;
  const { effect, condition } = ctrl.rule;
  if (!condition) return true;
  const value = condition.scope ? getByPath(data, scopePath(condition.scope)) : undefined;
  const matches = matchSchema(condition.schema, value);
  if (effect === "HIDE") return !matches;
  if (effect === "DISABLE") return true; // wir blenden nicht aus, lassen sichtbar
  return matches; // SHOW (Default)
}

export function countFields(schema: JsonSchema | undefined): number {
  if (!schema?.properties) return 0;
  let n = 0;
  for (const v of Object.values(schema.properties)) {
    if ((v as any).type === "object") n += countFields(v as JsonSchema);
    else n++;
  }
  return n;
}

/** Backend-Validierungsfehler in lesbares Deutsch uebersetzen. */
export function humanizeBackendError(detail: string | undefined): string {
  if (!detail) return "Unbekannter Fehler.";
  let m;
  if ((m = detail.match(/'([^']+)' is a required property \(Pfad: ([^)]*)\)/))) {
    const feld = humanize(m[1]);
    const grp = m[2] ? humanize(m[2].split("/").pop() ?? "") : "Hauptebene";
    return `Pflichtfeld nicht ausgefuellt: „${feld}" (in „${grp}").`;
  }
  if ((m = detail.match(/is too short \(Pfad: ([^)]*)\)/))) {
    return `Eingabe im Feld „${humanize(m[1].split("/").pop() ?? "")}" ist zu kurz.`;
  }
  if ((m = detail.match(/is not one of \[([^\]]+)\] \(Pfad: ([^)]*)\)/))) {
    return `Ungueltige Auswahl im Feld „${humanize(m[2].split("/").pop() ?? "")}".`;
  }
  if ((m = detail.match(/is not of type '([^']+)' \(Pfad: ([^)]*)\)/))) {
    return `Falscher Datentyp im Feld „${humanize(m[2].split("/").pop() ?? "")}" (erwartet: ${m[1]}).`;
  }
  return detail;
}

function humanize(s: string): string {
  return s
    .replace(/([A-Z])/g, " $1")
    .replace(/_/g, " ")
    .replace(/^./, (c) => c.toUpperCase())
    .trim();
}
