import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";

import {
  deactivateUser, getUser, listRoles, setUserPassword, setUserRoles, updateUser,
} from "@/api/admin";
import { useToast } from "@/components/Toaster";
import { formatDate } from "@/lib/utils";

export function UserEditPage() {
  const { id = "" } = useParams();
  const qc = useQueryClient();
  const { show } = useToast();
  const navigate = useNavigate();

  const { data: user, isLoading } = useQuery({
    queryKey: ["admin", "user", id],
    queryFn: () => getUser(id),
  });
  const { data: roles } = useQuery({ queryKey: ["admin", "roles"], queryFn: listRoles });

  const [displayName, setDisplayName] = useState("");
  const [email, setEmail] = useState("");
  const [isActive, setIsActive] = useState(true);
  const [roleIds, setRoleIds] = useState<string[]>([]);
  const [password, setPassword] = useState("");

  useEffect(() => {
    if (!user || !roles) return;
    setDisplayName(user.display_name);
    setEmail(user.email || "");
    setIsActive(user.is_active);
    const idByName = Object.fromEntries(roles.map((r) => [r.name, r.id]));
    setRoleIds(user.roles.map((n) => idByName[n]).filter(Boolean));
  }, [user, roles]);

  const updateMut = useMutation({
    mutationFn: () => updateUser(id, {
      display_name: displayName, email: email || null, is_active: isActive,
    }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["admin", "user", id] });
      qc.invalidateQueries({ queryKey: ["admin", "users"] });
      show("Stammdaten gespeichert.");
    },
    onError: (e) => show((e as Error).message, "error"),
  });

  const rolesMut = useMutation({
    mutationFn: () => setUserRoles(id, roleIds),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["admin", "user", id] });
      show("Rollen aktualisiert.");
    },
    onError: (e) => show((e as Error).message, "error"),
  });

  const pwMut = useMutation({
    mutationFn: () => setUserPassword(id, password),
    onSuccess: () => { show("Passwort gesetzt."); setPassword(""); },
    onError: (e) => show((e as Error).message, "error"),
  });

  const deactivateMut = useMutation({
    mutationFn: () => deactivateUser(id),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["admin", "users"] });
      show("User deaktiviert.");
      navigate("/admin/users");
    },
    onError: (e) => show((e as Error).message, "error"),
  });

  if (isLoading || !user) return <div className="paper py-10 text-center text-quiet">Lade …</div>;

  return (
    <section>
      <header className="page-header">
        <p className="eyebrow mb-3">Admin · User</p>
        <h2 className="page-title">{user.display_name}</h2>
        <p className="page-lead font-mono text-[13px]">
          {user.username} · {user.auth_source} · zuletzt eingeloggt {formatDate(user.last_login_at) || "nie"}
        </p>
      </header>

      <div className="grid gap-6 lg:grid-cols-2">
        <Card title="Stammdaten">
          <Field label="Anzeigename">
            <input className="input" value={displayName} onChange={(e) => setDisplayName(e.target.value)} />
          </Field>
          <Field label="E-Mail">
            <input className="input" type="email" value={email} onChange={(e) => setEmail(e.target.value)} />
          </Field>
          <label className="inline-flex items-center gap-2 text-[13px]">
            <input type="checkbox" checked={isActive} onChange={(e) => setIsActive(e.target.checked)} />
            aktiv
          </label>
          <button className="btn btn-primary mt-2 self-start" onClick={() => updateMut.mutate()} disabled={updateMut.isPending}>
            Speichern
          </button>
        </Card>

        <Card title="Rollen">
          {roles?.map((r) => (
            <label key={r.id} className="inline-flex items-center gap-2 text-[13px] mr-2 mb-2
                                          border border-rule rounded-md px-2 py-1 cursor-pointer hover:bg-bg/50">
              <input type="checkbox"
                     checked={roleIds.includes(r.id)}
                     onChange={(e) => {
                       setRoleIds((prev) => e.target.checked ? [...prev, r.id] : prev.filter((x) => x !== r.id));
                     }} />
              {r.name}
            </label>
          ))}
          <button className="btn btn-primary mt-3 self-start" onClick={() => rolesMut.mutate()} disabled={rolesMut.isPending}>
            Rollen speichern
          </button>
        </Card>

        {user.auth_source === "local" && (
          <Card title="Passwort zuruecksetzen">
            <Field label="Neues Passwort">
              <input type="password" className="input" minLength={8}
                     value={password} onChange={(e) => setPassword(e.target.value)} />
            </Field>
            <button className="btn btn-warn self-start" onClick={() => pwMut.mutate()}
                    disabled={!password || pwMut.isPending}>
              Setzen
            </button>
          </Card>
        )}

        <Card title="Deaktivieren">
          <p className="hint">Der User kann sich danach nicht mehr einloggen. Audit-Bezuege bleiben.</p>
          <button className="btn btn-bad self-start mt-2"
                  onClick={() => { if (confirm(`User ${user.username} wirklich deaktivieren?`)) deactivateMut.mutate(); }}
                  disabled={deactivateMut.isPending || !user.is_active}>
            Deaktivieren
          </button>
        </Card>
      </div>
    </section>
  );
}

function Card({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div className="paper flex flex-col gap-3">
      <p className="label-mono">{title}</p>
      {children}
    </div>
  );
}

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <label className="flex flex-col gap-1">
      <span className="label-mono">{label}</span>
      {children}
    </label>
  );
}
