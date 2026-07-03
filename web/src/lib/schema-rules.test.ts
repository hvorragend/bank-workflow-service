/**
 * Vitest-Smoke-Test fuer den Schema-Renderer-Helfer. Testet die Logik, die
 * 1:1 aus der Vue-Demo portiert wurde — Conditional-Rendering, Pflichtfeld-
 * Erkennung und Daten-Initialisierung.
 */
import { describe, expect, test } from "vitest";

import {
  findMissingRequired,
  initFormData,
  isRequired,
  isVisible,
  pruneEmpty,
  resolveScope,
  scopeKey,
  scopePath,
  setByPathImmutable,
} from "./schema-rules";
import { compareSemver } from "./utils";

const SCHEMA = {
  type: "object",
  required: ["a", "b"],
  properties: {
    a: { type: "string" },
    b: {
      type: "object",
      required: ["aktiv", "begruendung"],
      properties: {
        aktiv: { type: "boolean" },
        begruendung: { type: "string", minLength: 10 },
      },
    },
  },
};

describe("scope helpers", () => {
  test("scopeKey extracts last segment", () => {
    expect(scopeKey("#/properties/b/properties/begruendung")).toBe("begruendung");
  });
  test("scopePath strips 'properties' nodes", () => {
    expect(scopePath("#/properties/b/properties/aktiv")).toEqual(["b", "aktiv"]);
  });
  test("resolveScope returns the field schema", () => {
    expect(resolveScope(SCHEMA, "#/properties/b/properties/aktiv")?.type).toBe("boolean");
  });
});

describe("isRequired", () => {
  test("erkennt ein Pflichtfeld auf erster Ebene", () => {
    expect(isRequired("#/properties/a", SCHEMA)).toBe(true);
  });
  test("erkennt ein Pflichtfeld in einer Untergruppe", () => {
    expect(isRequired("#/properties/b/properties/aktiv", SCHEMA)).toBe(true);
  });
});

describe("initFormData", () => {
  test("Booleans bleiben undefined, Strings werden leerer String", () => {
    const init = initFormData(SCHEMA);
    expect(init.a).toBe("");
    expect(init.b.aktiv).toBeUndefined();
    expect(init.b.begruendung).toBe("");
  });
});

describe("pruneEmpty", () => {
  test("entfernt undefined und leere Strings", () => {
    const cleaned = pruneEmpty({
      a: "",
      b: { aktiv: undefined, begruendung: "Drei Saetze." },
    });
    expect(cleaned).toEqual({ b: { begruendung: "Drei Saetze." } });
  });
});

describe("setByPathImmutable", () => {
  test("setzt verschachtelten Wert ohne das Original zu mutieren", () => {
    const orig = { b: { aktiv: false } };
    const next = setByPathImmutable(orig, ["b", "aktiv"], true);
    expect(next.b.aktiv).toBe(true);
    expect(orig.b.aktiv).toBe(false); // Original unveraendert
    expect(next).not.toBe(orig);
    expect(next.b).not.toBe(orig.b);
  });
});

describe("compareSemver", () => {
  test("numerischer statt lexikographischer Vergleich", () => {
    expect(compareSemver("1.10.0", "1.9.0")).toBeGreaterThan(0);
    expect(compareSemver("2.0.0", "10.0.0")).toBeLessThan(0);
    expect(compareSemver("1.2.3", "1.2.3")).toBe(0);
    expect(compareSemver("v1.0.0", "1.0.0")).toBe(0);
  });
});

describe("findMissingRequired", () => {
  const ui = {
    elements: [
      {
        elements: [
          { scope: "#/properties/a" },
          { scope: "#/properties/b/properties/begruendung" },
        ],
      },
    ],
  };
  test("meldet leere sichtbare Pflichtfelder", () => {
    const missing = findMissingRequired(ui, SCHEMA, { a: "", b: { begruendung: "" } });
    expect(missing).toContain("#/properties/a");
    expect(missing).toContain("#/properties/b/properties/begruendung");
  });
  test("ausgefuellte Pflichtfelder fehlen nicht", () => {
    const missing = findMissingRequired(ui, SCHEMA, { a: "x", b: { begruendung: "text" } });
    expect(missing).toEqual([]);
  });
});

describe("isVisible (Conditional Rules)", () => {
  test("ohne Rule: immer sichtbar", () => {
    expect(isVisible({ scope: "#/properties/a" }, {})).toBe(true);
  });
  test("SHOW + const: sichtbar wenn Wert matcht", () => {
    const ctrl = {
      scope: "#/properties/b/properties/begruendung",
      rule: {
        effect: "SHOW" as const,
        condition: {
          scope: "#/properties/b/properties/aktiv",
          schema: { const: true },
        },
      },
    };
    expect(isVisible(ctrl, { b: { aktiv: true } })).toBe(true);
    expect(isVisible(ctrl, { b: { aktiv: false } })).toBe(false);
    expect(isVisible(ctrl, {})).toBe(false);
  });
  test("HIDE + const: invertiert", () => {
    const ctrl = {
      scope: "#/properties/b/properties/begruendung",
      rule: {
        effect: "HIDE" as const,
        condition: {
          scope: "#/properties/b/properties/aktiv",
          schema: { const: true },
        },
      },
    };
    expect(isVisible(ctrl, { b: { aktiv: true } })).toBe(false);
    expect(isVisible(ctrl, { b: { aktiv: false } })).toBe(true);
  });
});
