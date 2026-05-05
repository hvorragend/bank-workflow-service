"""JSON-Schema-Diff fuer den Admin-Bereich.

Erkennt fuer Audit-Zwecke die wichtigsten strukturellen Aenderungen zwischen
zwei FormDefinition-Schemas:

- Felder, die hinzugekommen oder weggefallen sind
- Pflicht-Wechsel (required: true/false) je Feld
- Type-/Format-/Constraint-Wechsel (minLength, enum, …)

Ist bewusst kein vollstaendiger JSON-Schema-Diff (Anker, anyOf, allOf-Branches
werden ignoriert) — fuer die Standard-Maskenstrukturen, die wir hier fuehren,
reicht das. Spaetere Erweiterung folgt den realen Anwendungsfaellen.
"""
from __future__ import annotations

from typing import Any, Iterable, Literal

DiffKind = Literal[
    "field_added",
    "field_removed",
    "type_changed",
    "required_changed",
    "constraint_changed",
    "enum_changed",
]


def diff_schemas(old: dict[str, Any], new: dict[str, Any]) -> list[dict[str, Any]]:
    """Vergleicht zwei JSON-Schemas. Gibt eine flache Liste von Diff-Einträgen zurueck."""
    out: list[dict[str, Any]] = []
    _walk("", old or {}, new or {}, out)
    return out


def _walk(path: str, old: dict[str, Any], new: dict[str, Any], out: list[dict[str, Any]]) -> None:
    old_props = (old.get("properties") or {}) if isinstance(old, dict) else {}
    new_props = (new.get("properties") or {}) if isinstance(new, dict) else {}
    old_required = set(old.get("required") or []) if isinstance(old, dict) else set()
    new_required = set(new.get("required") or []) if isinstance(new, dict) else set()

    keys = sorted(set(old_props) | set(new_props))
    for k in keys:
        sub_path = f"{path}/{k}" if path else k
        if k in new_props and k not in old_props:
            out.append({"kind": "field_added", "path": sub_path, "before": None, "after": new_props[k]})
            continue
        if k in old_props and k not in new_props:
            out.append({"kind": "field_removed", "path": sub_path, "before": old_props[k], "after": None})
            continue

        old_field = old_props[k]
        new_field = new_props[k]

        # required-Wechsel
        was_required = k in old_required
        is_required = k in new_required
        if was_required != is_required:
            out.append({
                "kind": "required_changed",
                "path": sub_path,
                "before": was_required,
                "after": is_required,
            })

        # Type-Wechsel
        if old_field.get("type") != new_field.get("type"):
            out.append({
                "kind": "type_changed",
                "path": sub_path,
                "before": old_field.get("type"),
                "after": new_field.get("type"),
            })

        # Constraint-Wechsel (minLength, maxLength, format, pattern, minimum, maximum)
        for attr in ("minLength", "maxLength", "format", "pattern", "minimum", "maximum"):
            if old_field.get(attr) != new_field.get(attr):
                out.append({
                    "kind": "constraint_changed",
                    "path": f"{sub_path} ({attr})",
                    "before": old_field.get(attr),
                    "after": new_field.get(attr),
                })

        # Enum-Diff
        if old_field.get("enum") != new_field.get("enum"):
            out.append({
                "kind": "enum_changed",
                "path": sub_path,
                "before": old_field.get("enum"),
                "after": new_field.get("enum"),
            })

        # Rekursion in Subschema
        if old_field.get("type") == "object" and new_field.get("type") == "object":
            _walk(sub_path, old_field, new_field, out)


def summarize(diffs: Iterable[dict[str, Any]]) -> dict[str, int]:
    """Aggregierte Zaehlung fuer kompakte Anzeige."""
    counts: dict[str, int] = {}
    for d in diffs:
        counts[d["kind"]] = counts.get(d["kind"], 0) + 1
    return counts
