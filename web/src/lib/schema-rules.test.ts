/**
 * Vitest-Smoke-Test fuer den Schema-Renderer-Helfer. Testet die Logik, die
 * 1:1 aus der Vue-Demo portiert wurde — Conditional-Rendering, Pflichtfeld-
 * Erkennung und Daten-Initialisierung.
 */
import { describe, expect, test } from "vitest";

import {
  initFormData,
  isRequired,
  isVisible,
  pruneEmpty,
  resolveScope,
  scopeKey,
  scopePath,
} from "./schema-rules";

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
