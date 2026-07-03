import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useMemo, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";

import {
  deleteRole, getRole, listPermissions, setRolePermissions, updateRole,
} from "@/api/admin";
import { QueryError } from "@/components/QueryStates";
import { useToast } from "@/components/Toaster";

export function RoleEditPage() {
  const { id = "" } = useParams();
  const qc = useQueryClient();
  const { show } = useToast();
  const navigate = useNavigate();

  const { data: role, isLoading, error } = useQuery({
    queryKey: ["admin", "role", id], queryFn: () => getRole(id),
  });
  const { data: catalog } = useQuery({
    queryKey: ["admin", "permissions"], queryFn: listPermissions,
  });

  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [selected, setSelected] = useState<Set<string>>(new Set());

  useEffect(() => {
    if (!role) return;
    setName(role.name);
    setDescription(role.description ?? "");
    setSelected(new Set(role.permission_codes));
  }, [role]);

  const grouped = useMemo(() => {
    const map: Record<string, typeof catalog> = {};
    for (const p of catalog ?? []) (map[p.area] ??= []).push(p);
    return map;
  }, [catalog]);

  const updateMut = useMutation({
    mutationFn: () => updateRole(id, { name, description: description || null }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["admin", "role", id] });
      qc.invalidateQueries({ queryKey: ["admin", "roles"] });
      show("Rolle gespeichert.");
    },
    onError: (e) => show((e as Error).message, "error"),
  });

  const permsMut = useMutation({
    mutationFn: () => setRolePermissions(id, Array.from(selected)),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["admin", "role", id] });
      show("Permissions gespeichert.");
    },
    onError: (e) => show((e as Error).message, "error"),
  });

  const deleteMut = useMutation({
    mutationFn: () => deleteRole(id),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["admin", "roles"] });
      show("Rolle gelöscht.");
      navigate("/admin/roles");
    },
    onError: (e) => show((e as Error).message, "error"),
  });

  if (error) return <QueryError error={error} />;
  if (isLoading || !role) return <div className="paper py-10 text-center text-quiet">Lade …</div>;

  return (
    <section>
      <header className="page-header">
        <p className="eyebrow mb-3">Admin · Rolle</p>
        <h2 className="page-title">{role.name} {role.is_system && <span className="badge ml-3">system</span>}</h2>
      </header>

      <div className="grid gap-6 lg:grid-cols-[300px_minmax(0,1fr)]">
        <div className="paper flex flex-col gap-3">
          <label className="flex flex-col gap-1">
            <span className="label-mono">Name</span>
            <input className="input" value={name} disabled={role.is_system}
                   onChange={(e) => setName(e.target.value)} />
          </label>
          <label className="flex flex-col gap-1">
            <span className="label-mono">Beschreibung</span>
            <textarea className="input" rows={3} value={description}
                      onChange={(e) => setDescription(e.target.value)} />
          </label>
          <button className="btn btn-primary self-start" onClick={() => updateMut.mutate()}
                  disabled={updateMut.isPending}>Speichern</button>
          {!role.is_system && (
            <button className="btn btn-bad self-start mt-4"
                    onClick={() => { if (confirm(`Rolle ${role.name} wirklich löschen?`)) deleteMut.mutate(); }}
                    disabled={deleteMut.isPending}>
              Rolle löschen
            </button>
          )}
        </div>

        <div className="paper">
          <p className="label-mono mb-3">Permissions ({selected.size} / {catalog?.length ?? 0})</p>
          <div className="flex flex-col gap-4">
            {Object.entries(grouped).map(([area, perms]) => (
              <div key={area}>
                <p className="font-mono text-[11px] uppercase tracking-wider text-quiet mb-2">{area}</p>
                <div className="flex flex-col gap-1">
                  {perms?.map((p) => (
                    <label key={p.code} className="flex items-start gap-2 text-[13px] cursor-pointer">
                      <input
                        type="checkbox"
                        className="mt-1"
                        checked={selected.has(p.code)}
                        onChange={(e) => {
                          setSelected((prev) => {
                            const next = new Set(prev);
                            if (e.target.checked) next.add(p.code); else next.delete(p.code);
                            return next;
                          });
                        }}
                      />
                      <span>
                        <code className="text-ink">{p.code}</code>
                        <span className="block text-quiet text-[12px]">{p.description}</span>
                      </span>
                    </label>
                  ))}
                </div>
              </div>
            ))}
          </div>
          <button className="btn btn-primary mt-4" onClick={() => permsMut.mutate()}
                  disabled={permsMut.isPending}>
            Permissions speichern
          </button>
        </div>
      </div>
    </section>
  );
}
