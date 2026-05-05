import { LogOut } from "lucide-react";
import { NavLink, Outlet, useNavigate } from "react-router-dom";

import { useAuth } from "@/auth/AuthContext";
import { cn } from "@/lib/utils";

interface Tab { to: string; label: string; end?: boolean }

const baseTabs: Tab[] = [
  { to: "/",             label: "Aktuelles", end: true },
  { to: "/antraege",     label: "Antraege" },
  { to: "/archiv",       label: "Archiv" },
  { to: "/definitionen", label: "Definitionen" },
  { to: "/neu",          label: "Neuer Antrag" },
];

const adminTabs: Tab[] = [
  { to: "/admin",        label: "Admin",     end: true },
  { to: "/admin/audit",  label: "Audit" },
];

export function Layout() {
  const { state, logout } = useAuth();
  const navigate = useNavigate();
  const user = state.status === "authenticated" ? state.user : null;
  const isAdmin = !!user?.roles.includes("Admin");
  const tabs = isAdmin ? [...baseTabs, ...adminTabs] : baseTabs;

  return (
    <>
      <header className="sticky top-0 z-10 border-b border-rule bg-bg/95 backdrop-blur">
        <div className="mx-auto max-w-[1180px] px-10 pt-7">
          <div className="flex items-baseline gap-5 border-b border-rule-soft pb-6">
            <h1 className="m-0 font-display font-medium text-[34px] tracking-tightish font-display">
              Bank Workflow
            </h1>
            <p className="m-0 text-[13px] text-muted tracking-wide">
              Versionierter Antrags- und Genehmigungsservice
            </p>
            <div className="ml-auto flex items-center gap-4">
              {user && (
                <>
                  <div className="text-right leading-tight">
                    <div className="text-[13px] text-ink">{user.name || user.username}</div>
                    <div className="font-mono text-[10px] uppercase tracking-widest text-quiet">
                      {user.roles.join(" · ") || "ohne Rolle"}
                    </div>
                  </div>
                  <button
                    onClick={async () => {
                      await logout();
                      navigate("/login", { replace: true });
                    }}
                    className="inline-flex items-center gap-1.5 border border-rule px-3 py-1.5 text-xs text-muted hover:bg-ink hover:text-paper hover:border-ink transition"
                    title="Abmelden"
                  >
                    <LogOut size={14} /> Abmelden
                  </button>
                </>
              )}
            </div>
          </div>
          <nav className="-mt-px flex">
            {tabs.map((t) => (
              <NavLink
                key={t.to}
                to={t.to}
                end={t.end}
                className={({ isActive }) =>
                  cn(
                    "border-b-2 border-transparent pb-3.5 pt-3.5 mr-8 font-body text-[13px] font-medium uppercase tracking-wide text-muted hover:text-ink transition",
                    isActive && "text-ink border-b-accent",
                  )
                }
              >
                {t.label}
              </NavLink>
            ))}
          </nav>
        </div>
      </header>
      <main className="mx-auto max-w-[1180px] px-10 py-14 pb-32">
        <Outlet />
      </main>
    </>
  );
}
