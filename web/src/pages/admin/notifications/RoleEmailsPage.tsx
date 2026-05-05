import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useState } from "react";

import { listRoleEmails, listRoles, setRoleEmails } from "@/api/admin";
import { useToast } from "@/components/Toaster";

export function RoleEmailsPage() {
  const qc = useQueryClient();
  const { show } = useToast();
  const { data: emails } = useQuery({
    queryKey: ["admin", "role-emails"], queryFn: listRoleEmails,
  });
  const { data: roles } = useQuery({ queryKey: ["admin", "roles"], queryFn: listRoles });

  const [editing, setEditing] = useState<Record<string, string>>({});

  useEffect(() => {
    if (!roles || !emails) return;
    const init: Record<string, string> = {};
    for (const r of roles) {
      init[r.id] = emails.filter((e) => e.role_id === r.id).map((e) => e.email).join("\n");
    }
    setEditing(init);
  }, [roles, emails]);

  const mut = useMutation({
    mutationFn: ({ roleId, list }: { roleId: string; list: string[] }) =>
      setRoleEmails(roleId, list),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["admin", "role-emails"] });
      show("Empfaenger gespeichert.");
    },
    onError: (e) => show((e as Error).message, "error"),
  });

  return (
    <section>
      <header className="page-header">
        <p className="eyebrow mb-3">Admin · Notifications</p>
        <h2 className="page-title">Rollen-Empfaenger</h2>
        <p className="page-lead">
          Zusaetzliche Mail-Adressen pro Rolle (Gruppenpostfaecher). Werden zu den
          Adressen aktiver User mit derselben Rolle hinzugefuegt — eine Adresse
          pro Zeile.
        </p>
      </header>
      <div className="grid gap-4 md:grid-cols-2">
        {roles?.map((r) => (
          <div key={r.id} className="paper">
            <p className="label-mono mb-2">{r.name}</p>
            <textarea className="input font-mono text-[12px]" rows={5}
                      value={editing[r.id] ?? ""}
                      onChange={(e) => setEditing((prev) => ({ ...prev, [r.id]: e.target.value }))} />
            <button className="btn btn-primary mt-2" disabled={mut.isPending}
                    onClick={() => mut.mutate({
                      roleId: r.id,
                      list: (editing[r.id] ?? "").split(/\r?\n/).map((l) => l.trim()).filter(Boolean),
                    })}>
              Speichern
            </button>
          </div>
        ))}
      </div>
    </section>
  );
}
