import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { useNavigate } from "react-router-dom";

import { createUser, listRoles } from "@/api/admin";
import { useToast } from "@/components/Toaster";

export function UserCreatePage() {
  const navigate = useNavigate();
  const qc = useQueryClient();
  const { show } = useToast();
  const { data: roles } = useQuery({ queryKey: ["admin", "roles"], queryFn: listRoles });

  const [username, setUsername] = useState("");
  const [displayName, setDisplayName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [roleIds, setRoleIds] = useState<string[]>([]);

  const mut = useMutation({
    mutationFn: createUser,
    onSuccess: (u) => {
      qc.invalidateQueries({ queryKey: ["admin", "users"] });
      show(`User ${u.username} angelegt.`);
      navigate(`/admin/users/${u.id}`);
    },
    onError: (e) => show(`Anlegen fehlgeschlagen: ${(e as Error).message}`, "error"),
  });

  function toggleRole(id: string) {
    setRoleIds((prev) => prev.includes(id) ? prev.filter((x) => x !== id) : [...prev, id]);
  }

  return (
    <section>
      <header className="page-header">
        <p className="eyebrow mb-3">Admin · Benutzer</p>
        <h2 className="page-title">Neuer User</h2>
        <p className="page-lead">Anlegen lokaler User. LDAP-User entstehen automatisch beim Login bzw. Sync.</p>
      </header>

      <form
        className="paper max-w-[640px] flex flex-col gap-4"
        onSubmit={(e) => { e.preventDefault(); mut.mutate({
          username, display_name: displayName, email: email || null,
          password, role_ids: roleIds,
        }); }}
      >
        <Field label="Username">
          <input className="input" value={username} onChange={(e) => setUsername(e.target.value)} required />
        </Field>
        <Field label="Anzeigename">
          <input className="input" value={displayName} onChange={(e) => setDisplayName(e.target.value)} required />
        </Field>
        <Field label="E-Mail">
          <input type="email" className="input" value={email} onChange={(e) => setEmail(e.target.value)} />
        </Field>
        <Field label="Passwort (mindestens 8 Zeichen)">
          <input type="password" className="input" minLength={8} value={password}
                 onChange={(e) => setPassword(e.target.value)} required />
        </Field>
        <Field label="Rollen">
          <div className="flex flex-wrap gap-2">
            {roles?.map((r) => (
              <label key={r.id} className="inline-flex items-center gap-1.5 text-[13px] cursor-pointer
                                            border border-rule rounded-md px-2 py-1 hover:bg-bg/50">
                <input type="checkbox" checked={roleIds.includes(r.id)} onChange={() => toggleRole(r.id)} />
                {r.name}
              </label>
            ))}
          </div>
        </Field>
        <div className="flex gap-2 pt-2">
          <button type="submit" className="btn btn-primary" disabled={mut.isPending}>
            Anlegen
          </button>
          <button type="button" className="btn btn-ghost" onClick={() => navigate(-1)}>
            Abbrechen
          </button>
        </div>
      </form>
    </section>
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
