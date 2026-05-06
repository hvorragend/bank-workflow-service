import { useMutation } from "@tanstack/react-query";
import { useState } from "react";
import { useNavigate } from "react-router-dom";

import { createRole } from "@/api/admin";
import { useToast } from "@/components/Toaster";

export function RoleCreatePage() {
  const { show } = useToast();
  const navigate = useNavigate();
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");

  const mut = useMutation({
    mutationFn: () => createRole({ name, description, permission_codes: [] }),
    onSuccess: (r) => {
      show(`Rolle ${r.name} angelegt — bitte Permissions auswaehlen.`);
      navigate(`/admin/roles/${r.id}`);
    },
    onError: (e) => show((e as Error).message, "error"),
  });

  return (
    <section>
      <header className="page-header">
        <p className="eyebrow mb-3">Admin · Rollen</p>
        <h2 className="page-title">Neue Rolle</h2>
      </header>
      <form className="paper max-w-[500px] flex flex-col gap-3"
            onSubmit={(e) => { e.preventDefault(); mut.mutate(); }}>
        <label className="flex flex-col gap-1">
          <span className="label-mono">Name</span>
          <input className="input" value={name} onChange={(e) => setName(e.target.value)} required />
        </label>
        <label className="flex flex-col gap-1">
          <span className="label-mono">Beschreibung</span>
          <textarea className="input" rows={3} value={description}
                    onChange={(e) => setDescription(e.target.value)} />
        </label>
        <div className="flex gap-2">
          <button type="submit" className="btn btn-primary" disabled={mut.isPending}>Anlegen</button>
          <button type="button" className="btn btn-ghost" onClick={() => navigate(-1)}>Abbrechen</button>
        </div>
      </form>
    </section>
  );
}
