import { useQuery } from "@tanstack/react-query";
import { ChevronRight, Clock, FileCheck2, FileX2, Inbox } from "lucide-react";
import { Link } from "react-router-dom";
import { Bar, BarChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";

import { getStats, listInstances } from "@/api/endpoints";
import { useAuth } from "@/auth/AuthContext";
import { StatusBadge } from "@/components/StatusBadge";
import { cn, formatDate, formatNumber, humanize, instanceTitle } from "@/lib/utils";
import type { FormInstance } from "@/types/api";

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
      <header className="page-header">
        <p className="eyebrow mb-3">Aktuelles</p>
        <h2 className="page-title">
          Guten Tag, {userName}.
        </h2>
        <p className="page-lead">
          Hier sehen Sie auf einen Blick, was Ihre Aufmerksamkeit braucht — und
          wie sich die Antragsbearbeitung in den letzten Tagen entwickelt hat.
        </p>
      </header>

      {/* Vier Kennzahlen-Kacheln */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-3 sm:gap-4 mb-8 sm:mb-10">
        <Tile
          label="Wartet auf mich"
          value={stats ? formatNumber(stats.waiting_for_me) : "—"}
          icon={<Inbox size={18} />}
          accent
        />
        <Tile
          label="In Prüfung gesamt"
          value={formatNumber(stats?.status_counts?.in_pruefung ?? 0)}
          icon={<Clock size={18} />}
        />
        <Tile
          label="Genehmigt (gesamt)"
          value={formatNumber(stats?.status_counts?.genehmigt ?? 0)}
          icon={<FileCheck2 size={18} />}
        />
        <Tile
          label="Letzte 7 Tage: erstellt"
          value={formatNumber(stats?.last7_created ?? 0)}
          icon={<FileX2 size={18} />}
        />
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-4 sm:gap-6">
        <ListCard
          title="Wartet auf meine Entscheidung"
          empty="Keine Anträge benötigen aktuell Ihre Entscheidung."
          items={pending}
          linkLabel="Alle offenen Anträge"
          linkTo="/antraege?wartet_auf_mich=true"
        />
        <ListCard
          title="Eigene Anträge"
          empty="Sie haben noch keine eigenen Anträge gestellt."
          items={own}
          linkLabel="Eigene anzeigen"
          linkTo="/antraege?mein=true"
        />
        <ListCard
          title="Zuletzt bewegt"
          empty="Keine Aktivität in den letzten Tagen."
          items={recent}
          linkLabel="Alle Anträge"
          linkTo="/antraege"
        />
      </div>

      {/* Chart */}
      {chartData.length > 0 && (
        <div className="paper mt-8 sm:mt-10">
          <h3 className="font-display font-semibold text-xl sm:text-2xl tracking-tightish m-0">
            Verteilung offener Anträge je Stage
          </h3>
          <p className="text-[13px] text-muted mt-1 mb-5 sm:mb-6">
            Wo stehen die Anträge in Prüfung gerade in der Genehmigungskette?
          </p>
          <div className="h-56 sm:h-64 -mx-2 sm:mx-0">
            <ResponsiveContainer>
              <BarChart data={chartData} margin={{ top: 10, right: 12, left: 0, bottom: 0 }}>
                <XAxis dataKey="stage" tick={{ fill: "hsl(215 14% 38%)", fontSize: 12 }} interval={0} />
                <YAxis allowDecimals={false} tick={{ fill: "hsl(215 14% 38%)", fontSize: 12 }} width={28} />
                <Tooltip
                  cursor={{ fill: "hsl(212 60% 94%)" }}
                  contentStyle={{
                    background: "white",
                    border: "1px solid hsl(214 15% 88%)",
                    borderRadius: "8px",
                    fontSize: "12px",
                    boxShadow: "0 8px 24px -8px rgb(15 23 42 / 0.18)",
                  }}
                />
                <Bar dataKey="Anzahl" fill="hsl(212 100% 21%)" radius={[6, 6, 0, 0]} />
              </BarChart>
            </ResponsiveContainer>
          </div>
        </div>
      )}

      {stats?.avg_decision_days != null && (
        <div className="hint hint-info mt-6">
          Durchschnittliche Bearbeitungsdauer (genehmigte Anträge):{" "}
          <strong className="text-ink font-semibold">
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
    <div className={cn("stat-tile", accent && "stat-tile-accent")}>
      <div className="flex items-center gap-2 text-quiet">
        <span className={cn(accent && "text-accent")}>{icon}</span>
        <span className="label-mono leading-tight">{label}</span>
      </div>
      <div className="mt-2 font-display font-semibold text-[26px] sm:text-[30px] lg:text-[34px] leading-none tracking-tightish text-ink">
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
    <div className="paper flex flex-col">
      <h3 className="font-display font-semibold text-lg sm:text-xl tracking-tightish m-0">
        {title}
      </h3>
      <ul className="mt-3 sm:mt-4 divide-y divide-rule-soft flex-1">
        {items && items.length > 0 ? (
          items.map((i) => (
            <li key={i.id} className="py-2.5 first:pt-0">
              <Link
                to={`/antraege/${i.id}`}
                className="block rounded-md hover:bg-bg -mx-2 px-2 py-2 transition-colors"
              >
                <div className="text-[14px] text-ink leading-snug font-medium">{instanceTitle(i)}</div>
                <div className="mt-1 flex flex-wrap items-center gap-x-2 gap-y-1 font-mono text-[11px] text-quiet">
                  <span className="text-accent">{i.schema_version}</span>
                  <StatusBadge value={i.status} />
                  <span>{formatDate(i.erstellt_am)}</span>
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
