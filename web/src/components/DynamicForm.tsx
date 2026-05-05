/**
 * JSON-Schema-Formular-Renderer.
 *
 * Liest UI-Schema (Gruppen + Controls + Notices) und rendert die Felder
 * dynamisch — inklusive Conditional-Visibility ueber rule.condition.
 */
import {
  getByPath,
  initFormData,
  isRequired,
  isVisible,
  resolveScope,
  scopeKey,
  scopePath,
  setByPath,
} from "@/lib/schema-rules";
import { humanize } from "@/lib/utils";
import { cn } from "@/lib/utils";
import type { JsonSchema, UiControl, UiSchema } from "@/types/api";

interface Props {
  jsonSchema: JsonSchema;
  uiSchema: UiSchema;
  data: Record<string, any>;
  onChange: (next: Record<string, any>) => void;
  /** Wenn true, werden Eingaben deaktiviert (Read-only-Detail-Ansicht). */
  readOnly?: boolean;
}

export function DynamicForm({ jsonSchema, uiSchema, data, onChange, readOnly = false }: Props) {
  function update(path: string[], value: any) {
    if (readOnly) return;
    // Tiefe Kopie reicht hier — Antragsdaten sind klein.
    const next = JSON.parse(JSON.stringify(data));
    setByPath(next, path, value);
    onChange(next);
  }

  return (
    <div>
      {uiSchema.elements.map((group) => (
        <fieldset
          key={group.label}
          className="border-0 border-t border-rule-soft py-8 first:border-t-0 first:pt-2 m-0"
        >
          <legend className="font-display font-display font-medium text-[22px] tracking-tightish px-4 -ml-4">
            {group.label}
          </legend>
          <div className="mt-5 grid grid-cols-1 sm:grid-cols-2 gap-x-8 gap-y-6">
            {group.elements.map((ctrl, idx) => (
              <Field
                key={ctrl.scope ?? `${group.label}-${idx}`}
                ctrl={ctrl}
                jsonSchema={jsonSchema}
                data={data}
                update={update}
                readOnly={readOnly}
              />
            ))}
          </div>
        </fieldset>
      ))}
    </div>
  );
}

interface FieldProps {
  ctrl: UiControl;
  jsonSchema: JsonSchema;
  data: Record<string, any>;
  update: (path: string[], value: any) => void;
  readOnly: boolean;
}

function Field({ ctrl, jsonSchema, data, update, readOnly }: FieldProps) {
  if (!isVisible(ctrl, data)) return null;

  if (ctrl.type === "Notice") {
    return (
      <div
        className={cn(
          "col-span-full border border-rule border-l-2 px-5 py-4 bg-bg",
          ctrl.level === "warning" && "border-l-warn bg-warn-soft",
          ctrl.level !== "warning" && "border-l-neutral",
        )}
      >
        <div className="font-display font-display font-medium text-[15px]">{ctrl.label}</div>
        <div className="mt-1 text-[13px] text-muted leading-relaxed">{ctrl.text}</div>
      </div>
    );
  }

  if (!ctrl.scope) return null;
  const fieldSchema = resolveScope(jsonSchema, ctrl.scope);
  const path = scopePath(ctrl.scope);
  const value = getByPath(data, path);
  const required = isRequired(ctrl.scope, jsonSchema);
  const isBool = fieldSchema?.type === "boolean";
  const isMulti = ctrl.options?.multi || (typeof fieldSchema?.minLength === "number" && fieldSchema.minLength > 30);
  const fullSpan = isBool || isMulti;

  return (
    <div className={cn("flex flex-col", fullSpan && "col-span-full", isBool && "flex-row items-center gap-3 py-1")}>
      <label
        className={cn(
          isBool
            ? "font-body text-sm text-ink"
            : "label-mono mb-2",
        )}
      >
        {humanize(scopeKey(ctrl.scope!))}
        {required && <span className="ml-1 text-accent">*</span>}
      </label>
      <FieldInput
        fieldSchema={fieldSchema}
        isMulti={!!isMulti}
        value={value}
        onChange={(v) => update(path, v)}
        readOnly={readOnly}
      />
      {fieldSchema?.description && !isBool && (
        <div className="mt-1.5 text-[12px] text-quiet">{fieldSchema.description}</div>
      )}
    </div>
  );
}

interface InputProps {
  fieldSchema: JsonSchema | undefined;
  isMulti: boolean;
  value: any;
  onChange: (v: any) => void;
  readOnly: boolean;
}

function FieldInput({ fieldSchema, isMulti, value, onChange, readOnly }: InputProps) {
  if (fieldSchema?.enum) {
    return (
      <select
        className="input"
        disabled={readOnly}
        value={value ?? ""}
        onChange={(e) => onChange(e.target.value)}
      >
        <option value="" disabled>
          — bitte waehlen —
        </option>
        {fieldSchema.enum.map((opt) => (
          <option key={opt} value={opt}>
            {opt}
          </option>
        ))}
      </select>
    );
  }
  if (fieldSchema?.type === "boolean") {
    return (
      <div className="flex gap-6 items-center pt-1">
        <label className="flex items-center gap-1.5 text-sm cursor-pointer">
          <input
            type="radio"
            disabled={readOnly}
            checked={value === true}
            onChange={() => onChange(true)}
          />
          Ja
        </label>
        <label className="flex items-center gap-1.5 text-sm cursor-pointer">
          <input
            type="radio"
            disabled={readOnly}
            checked={value === false}
            onChange={() => onChange(false)}
          />
          Nein
        </label>
      </div>
    );
  }
  if (fieldSchema?.format === "date") {
    return (
      <input
        type="date"
        className="input"
        disabled={readOnly}
        value={value ?? ""}
        onChange={(e) => onChange(e.target.value)}
      />
    );
  }
  if (isMulti) {
    return (
      <textarea
        className="input"
        rows={4}
        disabled={readOnly}
        value={value ?? ""}
        onChange={(e) => onChange(e.target.value)}
      />
    );
  }
  if (fieldSchema?.type === "number" || fieldSchema?.type === "integer") {
    return (
      <input
        type="number"
        className="input"
        disabled={readOnly}
        value={value ?? ""}
        onChange={(e) => onChange(Number(e.target.value))}
      />
    );
  }
  return (
    <input
      type="text"
      className="input"
      disabled={readOnly}
      value={value ?? ""}
      onChange={(e) => onChange(e.target.value)}
    />
  );
}

/** Eingabedaten sauber initialisieren — wird von Aufrufern beim Maskenwechsel genutzt. */
export function initDynamicData(schema: JsonSchema | undefined): Record<string, any> {
  return initFormData(schema) ?? {};
}
