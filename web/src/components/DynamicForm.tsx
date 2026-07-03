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
  setByPathImmutable,
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
  /** Scopes, die aktuell als fehlerhaft (z. B. leeres Pflichtfeld) markiert sind. */
  invalidScopes?: Set<string>;
}

/** Stabile, DOM-taugliche id aus einem Scope ableiten (fuer label htmlFor). */
function scopeToId(scope: string): string {
  return "f_" + scope.replace(/[^a-zA-Z0-9]+/g, "_").replace(/^_+|_+$/g, "");
}

export function DynamicForm({
  jsonSchema,
  uiSchema,
  data,
  onChange,
  readOnly = false,
  invalidScopes,
}: Props) {
  function update(path: string[], value: any) {
    if (readOnly) return;
    // Nur die Knoten entlang des Pfades klonen — kein Deep-Clone pro Tastendruck.
    onChange(setByPathImmutable(data, path, value));
  }

  return (
    <div>
      {uiSchema.elements.map((group) => (
        <fieldset
          key={group.label}
          className="border-0 border-t border-rule-soft pt-6 sm:pt-8 pb-2 first:border-t-0 first:pt-2 m-0"
        >
          <legend className="font-display font-semibold text-[18px] sm:text-[22px] tracking-tightish px-1 sm:px-2 -ml-1 sm:-ml-2 text-ink">
            {group.label}
          </legend>
          <div className="mt-4 sm:mt-5 grid grid-cols-1 sm:grid-cols-2 gap-x-6 sm:gap-x-8 gap-y-5 sm:gap-y-6">
            {group.elements.map((ctrl, idx) => (
              <Field
                key={ctrl.scope ?? `${group.label}-${idx}`}
                ctrl={ctrl}
                jsonSchema={jsonSchema}
                data={data}
                update={update}
                readOnly={readOnly}
                invalid={!!ctrl.scope && !!invalidScopes?.has(ctrl.scope)}
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
  invalid: boolean;
}

function Field({ ctrl, jsonSchema, data, update, readOnly, invalid }: FieldProps) {
  if (!isVisible(ctrl, data)) return null;

  if (ctrl.type === "Notice") {
    return (
      <div
        className={cn(
          "col-span-full rounded-md border border-rule-soft border-l-[3px] px-4 sm:px-5 py-3 sm:py-4 bg-bg",
          ctrl.level === "warning" && "border-l-warn bg-brand-soft",
          ctrl.level !== "warning" && "border-l-accent bg-accent-soft",
        )}
      >
        <div className="font-display font-semibold text-[14px] sm:text-[15px] text-ink">{ctrl.label}</div>
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
  // Textarea-Heuristik: explizit ueber options.multi oder ein grosszuegiges
  // maxLength — nicht ueber minLength (das sagt nichts ueber die Feldgroesse).
  const isMulti =
    ctrl.options?.multi ||
    (typeof (fieldSchema as any)?.maxLength === "number" && (fieldSchema as any).maxLength > 120);
  const fullSpan = isBool || isMulti;
  const fieldId = scopeToId(ctrl.scope);
  const labelText = humanize(scopeKey(ctrl.scope));
  const errId = `${fieldId}_err`;

  // Booleans als radiogruppe: fieldset/legend statt losem label.
  if (isBool) {
    return (
      <fieldset className="col-span-full flex flex-row items-center gap-3 py-1 border-0 m-0 p-0">
        <legend className="font-body text-sm text-ink float-left">
          {labelText}
          {required && <span className="ml-1 text-accent">*</span>}
        </legend>
        <div className="flex gap-6 items-center pt-1">
          <label className="flex items-center gap-1.5 text-sm cursor-pointer">
            <input
              type="radio"
              name={fieldId}
              disabled={readOnly}
              checked={value === true}
              onChange={() => update(path, true)}
            />
            Ja
          </label>
          <label className="flex items-center gap-1.5 text-sm cursor-pointer">
            <input
              type="radio"
              name={fieldId}
              disabled={readOnly}
              checked={value === false}
              onChange={() => update(path, false)}
            />
            Nein
          </label>
        </div>
        {invalid && <span id={errId} className="text-[12px] text-bad ml-2">Bitte auswählen.</span>}
      </fieldset>
    );
  }

  return (
    <div className={cn("flex flex-col", fullSpan && "col-span-full")}>
      <label htmlFor={fieldId} className="label-mono mb-2">
        {labelText}
        {required && <span className="ml-1 text-accent">*</span>}
      </label>
      <FieldInput
        id={fieldId}
        fieldSchema={fieldSchema}
        isMulti={!!isMulti}
        value={value}
        onChange={(v) => update(path, v)}
        readOnly={readOnly}
        invalid={invalid}
        errId={errId}
      />
      {invalid && (
        <div id={errId} className="mt-1.5 text-[12px] text-bad">Dieses Pflichtfeld ist erforderlich.</div>
      )}
      {fieldSchema?.description && (
        <div className="mt-1.5 text-[12px] text-quiet">{fieldSchema.description}</div>
      )}
    </div>
  );
}

interface InputProps {
  id: string;
  fieldSchema: JsonSchema | undefined;
  isMulti: boolean;
  value: any;
  onChange: (v: any) => void;
  readOnly: boolean;
  invalid: boolean;
  errId: string;
}

function FieldInput({ id, fieldSchema, isMulti, value, onChange, readOnly, invalid, errId }: InputProps) {
  const invalidProps = invalid
    ? { "aria-invalid": true as const, "aria-describedby": errId, className: "input border-bad" }
    : { className: "input" };

  if (fieldSchema?.enum) {
    return (
      <select
        id={id}
        {...invalidProps}
        disabled={readOnly}
        value={value ?? ""}
        onChange={(e) => onChange(e.target.value)}
      >
        <option value="" disabled>
          — bitte wählen —
        </option>
        {fieldSchema.enum.map((opt) => (
          <option key={opt} value={opt}>
            {opt}
          </option>
        ))}
      </select>
    );
  }
  if (fieldSchema?.format === "date") {
    return (
      <input
        id={id}
        type="date"
        {...invalidProps}
        disabled={readOnly}
        value={value ?? ""}
        onChange={(e) => onChange(e.target.value)}
      />
    );
  }
  if (isMulti) {
    return (
      <textarea
        id={id}
        {...invalidProps}
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
        id={id}
        type="number"
        {...invalidProps}
        disabled={readOnly}
        value={value ?? ""}
        onChange={(e) => {
          const raw = e.target.value;
          if (raw === "") {
            onChange(undefined); // Leerstring != 0
            return;
          }
          const n = Number(raw);
          onChange(Number.isNaN(n) ? undefined : n);
        }}
      />
    );
  }
  return (
    <input
      id={id}
      type="text"
      {...invalidProps}
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
