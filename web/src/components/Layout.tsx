import { LogOut, Menu, X } from "lucide-react";
import { useEffect, useState } from "react";
import { NavLink, Outlet, useLocation, useNavigate } from "react-router-dom";

import { useAuth } from "@/auth/AuthContext";
import { cn } from "@/lib/utils";

interface Tab { to: string; label: string; end?: boolean }

const baseTabs: Tab[] = [
  { to: "/",             label: "Aktuelles", end: true },
  { to: "/antraege",     label: "Anträge" },
  { to: "/archiv",       label: "Archiv" },
  { to: "/definitionen", label: "Definitionen" },
  { to: "/vertretungen", label: "Vertretungen" },
  { to: "/neu",          label: "Neuer Antrag" },
];

const adminTabs: Tab[] = [
  { to: "/admin",        label: "Admin" },
];

export function Layout() {
  const { state, logout } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();
  const user = state.status === "authenticated" ? state.user : null;
  const isAdmin = !!user?.permissions?.some((p) => p.startsWith("admin."));
  const tabs = isAdmin ? [...baseTabs, ...adminTabs] : baseTabs;

  const [mobileOpen, setMobileOpen] = useState(false);

  // Mobile-Menue beim Routenwechsel schliessen
  useEffect(() => { setMobileOpen(false); }, [location.pathname, location.search]);

  // Escape schliesst das Menue
  useEffect(() => {
    if (!mobileOpen) return;
    const onKey = (e: KeyboardEvent) => { if (e.key === "Escape") setMobileOpen(false); };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [mobileOpen]);

  // Body scroll lock waehrend das Menue offen ist
  useEffect(() => {
    if (mobileOpen) {
      const prev = document.body.style.overflow;
      document.body.style.overflow = "hidden";
      return () => { document.body.style.overflow = prev; };
    }
  }, [mobileOpen]);

  async function onLogout() {
    try {
      await logout();
    } finally {
      navigate("/login", { replace: true });
    }
  }

  return (
    <>
      <header className="sticky top-0 z-30 border-b border-rule bg-paper/95 backdrop-blur supports-[backdrop-filter]:bg-paper/80">
        <div className="mx-auto max-w-[1240px] px-4 sm:px-6 lg:px-10">
          {/* Obere Brand-Leiste */}
          <div className="flex items-center gap-4 py-4 sm:py-5">
            <Brand />
            <p className="hidden md:block m-0 text-[13px] text-muted">
              Versionierter Antrags- und Genehmigungsservice
            </p>
            <div className="ml-auto flex items-center gap-2 sm:gap-3">
              {user && (
                <>
                  <div className="hidden sm:block text-right leading-tight">
                    <div className="text-[13px] font-medium text-ink">
                      {user.name || user.username}
                    </div>
                    <div className="font-mono text-[10px] uppercase tracking-widest text-quiet">
                      {user.roles.join(" · ") || "ohne Rolle"}
                    </div>
                  </div>
                  <button
                    onClick={onLogout}
                    className="hidden sm:inline-flex items-center gap-1.5 rounded-md border border-rule px-3 py-1.5 text-xs font-medium text-muted hover:bg-accent hover:text-paper hover:border-accent transition-colors"
                    title="Abmelden"
                  >
                    <LogOut size={14} /> Abmelden
                  </button>
                </>
              )}
              <button
                type="button"
                onClick={() => setMobileOpen((v) => !v)}
                aria-expanded={mobileOpen}
                aria-controls="mobile-nav"
                aria-label={mobileOpen ? "Menü schließen" : "Menü öffnen"}
                className="lg:hidden inline-flex h-10 w-10 items-center justify-center rounded-md border border-rule text-ink hover:bg-accent-soft hover:border-accent-soft transition-colors"
              >
                {mobileOpen ? <X size={18} /> : <Menu size={18} />}
              </button>
            </div>
          </div>

          {/* Desktop-Navigation */}
          <nav className="hidden lg:flex -mb-px gap-1 overflow-x-auto">
            {tabs.map((t) => (
              <NavLink
                key={t.to}
                to={t.to}
                end={t.end}
                className={({ isActive }) =>
                  cn(
                    "relative whitespace-nowrap px-3 py-3 text-[13px] font-medium tracking-wide text-muted",
                    "border-b-2 border-transparent transition-colors hover:text-accent",
                    isActive && "text-accent border-b-accent",
                  )
                }
              >
                {t.label}
              </NavLink>
            ))}
          </nav>
        </div>

        {/* Mobile-Navigation: Slide-down-Panel */}
        {mobileOpen && (
          <div
            id="mobile-nav"
            className="lg:hidden border-t border-rule bg-paper animate-fadein"
          >
            <div className="mx-auto max-w-[1240px] px-4 sm:px-6 py-3">
              <nav className="flex flex-col">
                {tabs.map((t) => (
                  <NavLink
                    key={t.to}
                    to={t.to}
                    end={t.end}
                    className={({ isActive }) =>
                      cn(
                        "rounded-md px-3 py-3 text-[14px] font-medium",
                        "text-ink hover:bg-accent-soft transition-colors",
                        isActive && "bg-accent-soft text-accent",
                      )
                    }
                  >
                    {t.label}
                  </NavLink>
                ))}
              </nav>
              {user && (
                <div className="mt-3 border-t border-rule-soft pt-3 flex items-center justify-between gap-3">
                  <div className="leading-tight">
                    <div className="text-[13px] font-medium text-ink">
                      {user.name || user.username}
                    </div>
                    <div className="font-mono text-[10px] uppercase tracking-widest text-quiet">
                      {user.roles.join(" · ") || "ohne Rolle"}
                    </div>
                  </div>
                  <button
                    onClick={onLogout}
                    className="inline-flex items-center gap-1.5 rounded-md border border-rule px-3 py-2 text-xs font-medium text-muted hover:bg-accent hover:text-paper hover:border-accent transition-colors"
                  >
                    <LogOut size={14} /> Abmelden
                  </button>
                </div>
              )}
            </div>
          </div>
        )}
      </header>

      <main className="mx-auto max-w-[1240px] px-4 sm:px-6 lg:px-10 py-8 sm:py-10 lg:py-14 pb-24">
        <Outlet />
      </main>
    </>
  );
}

function Brand() {
  return (
    <NavLink to="/" className="flex items-center gap-3 group" aria-label="Bank Workflow — Startseite">
      <span
        aria-hidden
        className="inline-flex h-9 w-9 items-center justify-center rounded-md bg-accent text-paper shadow-card group-hover:bg-accent-hover transition-colors"
      >
        {/* Stilisiertes "BW"-Monogramm — schlicht, an Volksbanken-Markenform angelehnt */}
        <svg width="18" height="18" viewBox="0 0 20 20" fill="none" xmlns="http://www.w3.org/2000/svg" aria-hidden>
          <path d="M3 4h5.2a3.3 3.3 0 0 1 0 6.6H3z" stroke="currentColor" strokeWidth="1.6" strokeLinejoin="round"/>
          <path d="M3 10.6h5.6a3.3 3.3 0 0 1 0 6.6H3z" stroke="currentColor" strokeWidth="1.6" strokeLinejoin="round"/>
          <circle cx="15.4" cy="6.4" r="1.6" fill="currentColor"/>
        </svg>
      </span>
      <span className="flex flex-col leading-none">
        <span className="font-display font-semibold text-[17px] sm:text-[19px] tracking-tightish text-ink">
          Bank Workflow
        </span>
        <span className="hidden sm:block text-[10.5px] font-mono uppercase tracking-[0.18em] text-quiet mt-1">
          Genehmigungsservice
        </span>
      </span>
    </NavLink>
  );
}
