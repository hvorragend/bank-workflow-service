import { useState, type FormEvent } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Trash2, UserCheck } from "lucide-react";

import { ApiError } from "@/api/client";
import {
  createDelegation,
  deleteDelegation,
  listDelegations,
  type Delegation,
} from "@/api/endpoints";
import { LoadingCard, QueryError } from "@/components/QueryStates";
import { useToast } from "@/components/Toaster";
import { formatDate } from "@/lib/utils";

/** Formatiert ein reines "YYYY-MM-DD"-Datum ohne Uhrzeit deutsch. */
function formatDay(d: string): string {
  const dt = new Date(`${d}T00:00:00`);
  return Number.isNaN(dt.getTime()) ? d : dt.toLocaleDateString("de-DE");
}

export function DelegationsPage() {
  const qc = useQueryClient();
  const { show } = useToast();

  const [toUsername, setToUsername] = useState("");
  const [vonDatum, setVonDatum] = useState("");
  const [bisDatum, setBisDatum] = useState("");

  const { data, isLoading, error } = useQuery({
    queryKey: ["delegations"],
    queryFn: listDelegations,
  });

  const createMut = useMutation({
    mutationFn: createDelegation,
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["delegations"] });
      setToUsername("");
      setVonDatum("");
      setBisDatum("");
      show("Vertretung angelegt.");
    },
    onError: (err) => {
      const detail = err instanceof ApiError ? err.detail : (err as Error).message;
      show(`Anlegen fehlgeschlagen: ${detail}`, "error");
    },
  });

  const deleteMut = useMutation({
    mutationFn: (id: string) => deleteDelegation(id),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["delegations"] });
      show("Vertretung gelöscht.");
    },
    onError: (err) => {
      const detail = err instanceof ApiError ? err.detail : (err as Error).message;
      show(`Löschen fehlgeschlagen: ${detail}`, "error");
    },
  });

  function onSubmit(e: FormEvent) {
    e.preventDefault();
    if (!toUsername.trim() || !vonDatum || !bisDatum) {
      show("Bitte Vertreter und Zeitraum vollständig angeben.", "error");
      return;
    }
    if (bisDatum < vonDatum) {
      show("Das Bis-Datum darf nicht vor dem Von-Datum liegen.", "error");
      return;
    }
    createMut.mutate({
      to_username: toUsername.trim(),
      von_datum: vonDatum,
      bis_datum: bisDatum,
    });
  }

  return (
    <section>
      <header className="page-header">
        <p className="eyebrow mb-3">Self-Service</p>
        <h2 className="page-title">Meine Vertretungen</h2>
        <p className="page-lead">
          Legen Sie eine Vertretung fest, wenn Sie abwesend sind. In dem
          angegebenen Zeitraum kann die vertretende Person Ihre offenen Aufgaben
          mit übernehmen.
        </p>
      </header>

      <div className="grid grid-cols-1 lg:grid-cols-[1fr_360px] gap-6 lg:gap-8">
        {/* Liste */}
        <div>
          {isLoading ? (
            <LoadingCard label="Lade Vertretungen …" />
          ) : error ? (
            <QueryError error={error} />
          ) : !data || data.length === 0 ? (
            <div className="rounded-lg border border-dashed border-rule py-16 sm:py-20 text-center text-muted italic">
              Sie haben aktuell keine Vertretungen hinterlegt.
            </div>
          ) : (
            <ul className="list-card divide-y divide-rule-soft">
              {data.map((d: Delegation) => (
                <li
                  key={d.id}
                  className="grid grid-cols-[auto_1fr_auto] items-center gap-3 sm:gap-4 px-4 sm:px-6 py-4 bg-paper"
                >
                  <UserCheck size={18} className="text-muted shrink-0" />
                  <div className="min-w-0">
                    <div className="text-[14px] font-medium text-ink truncate">
                      {d.to_username}
                    </div>
                    <div className="font-mono text-[11px] text-quiet mt-0.5">
                      {formatDay(d.von_datum)} – {formatDay(d.bis_datum)}
                      <span className="hidden sm:inline">
                        {" · "}angelegt {formatDate(d.created_at)}
                      </span>
                    </div>
                  </div>
                  <button
                    type="button"
                    onClick={() => {
                      if (confirm(`Vertretung durch "${d.to_username}" wirklich löschen?`))
                        deleteMut.mutate(d.id);
                    }}
                    disabled={deleteMut.isPending}
                    className="text-muted hover:text-bad inline-flex items-center justify-center p-1.5 rounded-md hover:bg-bad-soft disabled:opacity-60"
                    title="Löschen"
                    aria-label="Löschen"
                  >
                    <Trash2 size={16} />
                  </button>
                </li>
              ))}
            </ul>
          )}
        </div>

        {/* Formular */}
        <aside className="paper lg:sticky lg:top-32 lg:self-start">
          <p className="eyebrow mb-4">Neue Vertretung</p>
          <form onSubmit={onSubmit} className="space-y-4">
            <div>
              <label className="label-mono mb-1.5 block">Vertreter (Benutzername)</label>
              <input
                className="input"
                value={toUsername}
                onChange={(e) => setToUsername(e.target.value)}
                placeholder="z. B. m.mustermann"
                required
              />
            </div>
            <div>
              <label className="label-mono mb-1.5 block">Von</label>
              <input
                type="date"
                className="input"
                value={vonDatum}
                onChange={(e) => setVonDatum(e.target.value)}
                required
              />
            </div>
            <div>
              <label className="label-mono mb-1.5 block">Bis</label>
              <input
                type="date"
                className="input"
                value={bisDatum}
                onChange={(e) => setBisDatum(e.target.value)}
                required
              />
            </div>
            <button type="submit" className="btn w-full" disabled={createMut.isPending}>
              {createMut.isPending ? "Speichere …" : "Vertretung anlegen"}
            </button>
          </form>
        </aside>
      </div>
    </section>
  );
}
