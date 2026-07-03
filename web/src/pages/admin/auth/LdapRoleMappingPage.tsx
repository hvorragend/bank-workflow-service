import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Trash2 } from "lucide-react";
import { useState } from "react";

import { createLdapMapping, deleteLdapMapping, listLdapMappings, listRoles } from "@/api/admin";
import { QueryError } from "@/components/QueryStates";
import { useToast } from "@/components/Toaster";

export function LdapRoleMappingPage() {
  const qc = useQueryClient();
  const { show } = useToast();
  const { data: mappings, isLoading, error } = useQuery({
    queryKey: ["admin", "ldap", "mappings"], queryFn: listLdapMappings,
  });
  const { data: roles } = useQuery({ queryKey: ["admin", "roles"], queryFn: listRoles });

  const [groupDn, setGroupDn] = useState("");
  const [roleId, setRoleId] = useState("");

  const addMut = useMutation({
    mutationFn: () => createLdapMapping({ group_dn: groupDn, role_id: roleId }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["admin", "ldap", "mappings"] });
      setGroupDn(""); setRoleId("");
      show("Mapping angelegt.");
    },
    onError: (e) => show((e as Error).message, "error"),
  });

  const delMut = useMutation({
    mutationFn: deleteLdapMapping,
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["admin", "ldap", "mappings"] });
      show("Mapping gelöscht.");
    },
    onError: (e) => show((e as Error).message, "error"),
  });

  return (
    <section>
      <header className="page-header">
        <p className="eyebrow mb-3">Admin · Auth</p>
        <h2 className="page-title">LDAP-Gruppen → Rollen-Mapping</h2>
        <p className="page-lead">
          Welche LDAP-Gruppe (per DN) gibt welcher App-Rolle Zugriff. Ein Mapping pro Zeile.
        </p>
      </header>

      <div className="paper mb-6 grid gap-3 md:grid-cols-[2fr_1fr_auto]">
        <label className="flex flex-col gap-1">
          <span className="label-mono">Group DN</span>
          <input id="mapping-group-dn" className="input" placeholder="cn=BWS-Admins,ou=Groups,dc=bank,dc=de"
                 value={groupDn} onChange={(e) => setGroupDn(e.target.value)} />
        </label>
        <label className="flex flex-col gap-1">
          <span className="label-mono">Rolle</span>
          <select id="mapping-role" className="input" value={roleId} onChange={(e) => setRoleId(e.target.value)}>
            <option value="">— Rolle —</option>
            {roles?.map((r) => <option key={r.id} value={r.id}>{r.name}</option>)}
          </select>
        </label>
        <button className="btn btn-primary self-end" disabled={!groupDn || !roleId || addMut.isPending}
                onClick={() => addMut.mutate()}>Hinzufügen</button>
      </div>

      <div className="paper p-0">
        {error ? (
          <QueryError error={error} />
        ) : isLoading ? (
          <div className="py-10 text-center text-quiet italic">Lade …</div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-[13px]">
              <thead>
                <tr className="text-left text-quiet">
                  <th scope="col" className="px-4 py-2 font-mono text-[11px] uppercase tracking-wider">Group DN</th>
                  <th scope="col" className="px-4 py-2 font-mono text-[11px] uppercase tracking-wider">Rolle</th>
                  <th />
                </tr>
              </thead>
              <tbody className="divide-y divide-rule-soft">
                {mappings?.map((m) => (
                  <tr key={m.id}>
                    <td className="px-4 py-3 font-mono text-[12px]">{m.group_dn}</td>
                    <td className="px-4 py-3">{m.role_name}</td>
                    <td className="px-4 py-3 text-right">
                      <button className="btn btn-ghost text-bad text-[12px] px-2 py-1"
                              onClick={() => { if (confirm("Mapping löschen?")) delMut.mutate(m.id); }}>
                        <Trash2 size={12} /> Löschen
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </section>
  );
}
