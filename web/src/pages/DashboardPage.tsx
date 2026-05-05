import { useQuery } from "@tanstack/react-query";
import { ChevronRight, Clock, FileCheck2, FileX2, Inbox } from "lucide-react";
import { Link } from "react-router-dom";
import { Bar, BarChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";

import { getStats, listInstances } from "@/api/endpoints";
import { useAuth } from "@/auth/AuthContext";
import { cn, formatDate, humanize } from "@/lib/utils";
import type { FormInstance } from "@/types/api";

function instanceTitle(i: FormInstance): string {
  return i.daten?.vorhaben?.titel || i.daten?.beschluss?.titel || "(ohne Titel)";
}

export function DashboardPage() {
  const { state } = useAuth();
  const userName = state.status === "authenticated" ? state.user.name || state.user.username : "";

  const { data: stats } = useQuery({ queryKey: ["stats"], queryFn: getStats });
  const { data: pending } = useQuery({
    queryKey: ["instances", { wartet_auf_mich: true }],
    queryFn: () => listInstances({ wartet_auf_mich: true, limit: 5 }),
  });
  const { data: own } = useQuery({
    queryKey: ["instances", { mein: true }],
    queryFn: () => listInstances({ mein: true, limit: 5 }),
  });
  const { data: recent } = useQuery({
    queryKey: ["instances", { recent: true }],
    queryFn: () => listInstances({ sort: "updated_desc", limit: 5 }),
  });

  const chartData = stats
    ? Object.entries(stats.stage_counts).map(([stage, count]) => ({
        stage: humanize(stage),
        Anzahl: count,
      }))
    : [];

  return (
    <section>
      <header className="mb-10 max-w-[720px]">
        <p className="eyebrow mb-3">Aktuelles</p>
        <h2 className="font-display font-display font-normal text-[40px] leading-[1.1] tracking-tightish">
          Guten Tag, {userName}.
        </h2>
        <p className="mt-4 text-[15.5px] text-muted">
          Hier sehen Sie auf einen Blick, was Ihre Aufmerksamkeit braucht — und
          wie sich die Antragsbearbeitung in den letzten Tagen entwickelt hat.
        </p>
      </header>

      {/* Vier Kennzahlen-Tiles */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4 mb-10">
        <Tile
          label="Wartet auf mich"
          value={stats?.waiting_for_me ?? "—"}
          icon={<Inbox size={18} />}
          accent
        />
        <Tile
          label="In Pruefung gesamt"
          value={stats?.status_counts?.in_pruefung ?? 0}
          icon={<Clock size={18} />}
        />
        <Tile
          label="Genehmigt (gesamt)"
          value={stats?.status_counts?.genehmigt ?? 0}
          icon={<FileCheck2 size={18} />}
        />
        <Tile
          label="Letzte 7 Tage: erstellt"
          value={stats?.last7_created ?? 0}
          icon={<FileX2 size={18} />}
        />
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        <ListCard
          title="Wartet auf meine Entscheidung"
          empty="Keine Antraege benoetigen aktuell Ihre Entscheidung."
          items={pending}
          linkLabel="Alle offenen Antraege"
          linkTo="/antraege?wartet_auf_mich=true"
        />
        <ListCard
          title="Eigene Antraege"
          empty="Sie haben noch keine eigenen Antraege gestellt."
          items={own}
          linkLabel="Eigene anzeigen"
          linkTo="/antraege?mein=true"
        />
        <ListCard
          title="Zuletzt bewegt"
          empty="Keine Aktivitaet in den letzten Tagen."
          items={recent}
          linkLabel="Alle Antraege"
          linkTo="/antraege"
        />
      </div>

      {/* Chart */}
      {chartData.length > 0 && (
        <div className="paper mt-10">
          <h3 className="font-display font-display font-medium text-2xl tracking-tightish m-0">
            Verteilung offener Antraege je Stage
          </h3>
          <p className="text-[13px] text-muted mt-1 mb-6">
            Wo stehen die in_pruefung-Antraege gerade in der Genehmigungskette?
          </p>
          <div className="h-64">
            <ResponsiveContainer>
              <BarChart data={chartData} margin={{ top: 10, right: 20, left: 0, bottom: 0 }}>
                <XAxis dataKey="stage" tick={{ fill: "hsl(35 6% 41%)", fontSize: 12 }} />
                <YAxis allowDecimals={false} tick={{ fill: "hsl(35 6% 41%)", fontSize: 12 }} />
                <Tooltip
                  cursor={{ fill: "hsl(43 30% 87%)" }}
                  contentStyle={{
                    background: "white",
                    border: "1px solid hsl(40 18% 80%)",
                    fontSize: "12px",
                  }}
                />
                <Bar dataKey="Anzahl" fill="hsl(0 53% 31%)" />
              </BarChart>
            </ResponsiveContainer>
          </div>
        </div>
      )}

      {stats?.avg_decision_days != null && (
        <div className="mt-6 border-l-2 border-rule bg-bg px-5 py-4 text-[13px] text-muted">
          Durchschnittliche Bearbeitungsdauer (genehmigte Antraege):{" "}
          <strong className="text-ink font-medium">
            {stats.avg_decision_days.toFixed(1)} Tage
          </strong>
        </div>
      )}
    </section>
  );
}

interface TileProps {
  label: string;
  value: number | string;
  icon: React.ReactNode;
  accent?: boolean;
}

function Tile({ label, value, icon, accent = false }: TileProps) {
  return (
    <div
      className={cn(
        "border border-rule bg-paper px-6 py-5",
        accent && "border-l-2 border-l-accent",
      )}
    >
      <div className="flex items-center gap-2 text-quiet">
        <span>{icon}</span>
        <span className="label-mono">{label}</span>
      </div>
      <div className="mt-2 font-display font-display font-medium text-[34px] leading-none tracking-tightish text-ink">
        {value}
      </div>
    </div>
  );
}

interface ListCardProps {
  title: string;
  empty: string;
  items?: FormInstance[];
  linkLabel: string;
  linkTo: string;
}

function ListCard({ title, empty, items, linkLabel, linkTo }: ListCardProps) {
  return (
    <div className="paper">
      <h3 className="font-display font-display font-medium text-xl tracking-tightish m-0">
        {title}
      </h3>
      <ul className="mt-4 divide-y divide-rule-soft">
        {items && items.length > 0 ? (
          items.map((i) => (
            <li key={i.id} className="py-3">
              <Link
                to={`/antraege/${i.id}`}
                className="block hover:bg-bg -mx-2 px-2 py-1.5 transition"
              >
                <div className="text-[14px] text-ink leading-snug">{instanceTitle(i)}</div>
                <div className="mt-1 font-mono text-[11px] text-quiet">
                  <span className="text-accent">{i.schema_version}</span> ·{" "}
                  <span className={`badge badge-${i.status} mr-1`}>{i.status}</span>
                  · {formatDate(i.erstellt_am)}
                </div>
              </Link>
            </li>
          ))
        ) : (
          <li className="py-6 text-quiet italic text-[13px]">{empty}</li>
        )}
      </ul>
      <div className="mt-4 pt-3 border-t border-rule-soft text-right">
        <Link
          to={linkTo}
          className="font-mono text-[11px] uppercase tracking-widest text-muted hover:text-accent inline-flex items-center gap-1"
        >
          {linkLabel} <ChevronRight size={12} />
        </Link>
      </div>
    </div>
  );
}
