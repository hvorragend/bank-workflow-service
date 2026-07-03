import { useRef, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Download, FileText, Paperclip, Trash2, Upload } from "lucide-react";

import {
  deleteAttachment,
  downloadAttachment,
  listAttachments,
  uploadAttachment,
  type Attachment,
} from "@/api/endpoints";
import { useToast } from "@/components/Toaster";
import { cn, formatDate } from "@/lib/utils";

const ALLOWED_EXTS = [".pdf", ".xlsx", ".docx", ".png", ".jpg", ".jpeg"];

interface Props {
  instanceId: string;
  /** Wenn true, wird Upload+Loeschen ausgeblendet (Antrag nicht mehr im Entwurf). */
  readOnly: boolean;
}

export function AttachmentsSection({ instanceId, readOnly }: Props) {
  const qc = useQueryClient();
  const { show } = useToast();
  const fileInput = useRef<HTMLInputElement>(null);
  const [dragActive, setDragActive] = useState(false);

  const { data: items, isLoading } = useQuery({
    queryKey: ["attachments", instanceId],
    queryFn: () => listAttachments(instanceId),
  });

  const uploadMut = useMutation({
    mutationFn: (file: File) => uploadAttachment(instanceId, file),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["attachments", instanceId] });
      show("Anhang hochgeladen.");
    },
    onError: (e) => show(`Upload fehlgeschlagen: ${(e as Error).message}`, "error"),
  });

  const deleteMut = useMutation({
    mutationFn: (attId: string) => deleteAttachment(instanceId, attId),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["attachments", instanceId] });
      show("Anhang gelöscht.");
    },
    onError: (e) => show(`Löschen fehlgeschlagen: ${(e as Error).message}`, "error"),
  });

  function handleFiles(files: FileList | null) {
    if (!files) return;
    Array.from(files).forEach((f) => uploadMut.mutate(f));
  }

  const downloadMut = useMutation({
    mutationFn: async (a: Attachment) => {
      const blob = await downloadAttachment(instanceId, a.id);
      const url = URL.createObjectURL(blob);
      const link = document.createElement("a");
      link.href = url;
      link.download = a.filename;
      link.click();
      URL.revokeObjectURL(url);
    },
    onError: (e) => show(`Download fehlgeschlagen: ${(e as Error).message}`, "error"),
  });

  return (
    <div className="paper mt-4 sm:mt-6 no-print">
      <div className="flex flex-col sm:flex-row sm:items-baseline sm:justify-between gap-3 sm:gap-4">
        <div>
          <h3 className="font-display font-semibold text-xl sm:text-2xl tracking-tightish m-0 inline-flex items-center gap-2">
            <Paperclip size={20} /> Anhänge
          </h3>
          <p className="text-[13px] text-muted mt-1">
            Bis zu 25 MB pro Datei. Erlaubt: {ALLOWED_EXTS.join(", ")}.
          </p>
        </div>
        {!readOnly && (
          <button className="btn whitespace-nowrap self-start" onClick={() => fileInput.current?.click()}>
            <Upload size={14} /> Datei hinzufügen
          </button>
        )}
        <input
          ref={fileInput}
          type="file"
          accept={ALLOWED_EXTS.join(",")}
          className="hidden"
          multiple
          onChange={(e) => handleFiles(e.target.files)}
        />
      </div>

      {!readOnly && (
        <div
          className={cn(
            "mt-5 rounded-lg border border-dashed border-rule px-6 py-8 sm:py-10 text-center text-sm text-muted transition-colors",
            dragActive && "bg-accent-soft border-accent",
          )}
          onDragOver={(e) => { e.preventDefault(); setDragActive(true); }}
          onDragLeave={() => setDragActive(false)}
          onDrop={(e) => {
            e.preventDefault();
            setDragActive(false);
            handleFiles(e.dataTransfer.files);
          }}
        >
          Dateien hier ablegen oder oben auf „Datei hinzufügen" klicken.
        </div>
      )}

      <ul className="mt-5 divide-y divide-rule-soft">
        {isLoading && <li className="py-4 text-quiet italic text-sm">Lade …</li>}
        {items && items.length === 0 && (
          <li className="py-6 text-quiet italic text-sm">Noch keine Anhänge.</li>
        )}
        {items?.map((a: Attachment) => (
          <li key={a.id} className="grid grid-cols-[auto_1fr_auto] sm:grid-cols-[auto_1fr_auto_auto] items-center gap-3 sm:gap-4 py-3">
            <FileText size={18} className="text-muted shrink-0" />
            <div className="min-w-0">
              <button
                type="button"
                onClick={() => downloadMut.mutate(a)}
                disabled={downloadMut.isPending}
                className="block text-left text-ink hover:text-accent text-[14px] truncate font-medium disabled:opacity-60"
              >
                {a.filename}
              </button>
              <div className="font-mono text-[11px] text-quiet mt-0.5 truncate">
                {(a.size_bytes / 1024).toFixed(1)} KB · SHA-256 {a.sha256.slice(0, 12)}…
                <span className="hidden sm:inline">
                  {" · "}hochgeladen von {a.uploaded_by} am {formatDate(a.uploaded_at)}
                </span>
              </div>
            </div>
            <button
              type="button"
              onClick={() => downloadMut.mutate(a)}
              disabled={downloadMut.isPending}
              className="text-muted hover:text-accent inline-flex items-center justify-center p-1.5 rounded-md hover:bg-accent-soft disabled:opacity-60"
              title="Herunterladen"
              aria-label="Herunterladen"
            >
              <Download size={16} />
            </button>
            {!readOnly && (
              <button
                onClick={() => {
                  if (confirm(`Anhang "${a.filename}" wirklich löschen?`)) deleteMut.mutate(a.id);
                }}
                disabled={deleteMut.isPending}
                className="col-start-3 sm:col-auto text-muted hover:text-bad inline-flex items-center justify-center p-1.5 rounded-md hover:bg-bad-soft"
                title="Löschen"
                aria-label="Löschen"
              >
                <Trash2 size={16} />
              </button>
            )}
          </li>
        ))}
      </ul>
    </div>
  );
}
