import { useRef, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Download, FileText, Paperclip, Trash2, Upload } from "lucide-react";

import {
  attachmentDownloadUrl,
  deleteAttachment,
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
      show("Anhang geloescht.");
    },
    onError: (e) => show(`Loeschen fehlgeschlagen: ${(e as Error).message}`, "error"),
  });

  function handleFiles(files: FileList | null) {
    if (!files) return;
    Array.from(files).forEach((f) => uploadMut.mutate(f));
  }

  return (
    <div className="paper mt-6 no-print">
      <div className="flex items-baseline justify-between gap-4">
        <div>
          <h3 className="font-display font-display font-medium text-2xl tracking-tightish m-0 inline-flex items-center gap-2">
            <Paperclip size={20} /> Anhaenge
          </h3>
          <p className="text-[13px] text-muted mt-1">
            Bis zu 25 MB pro Datei. Erlaubt: {ALLOWED_EXTS.join(", ")}.
          </p>
        </div>
        {!readOnly && (
          <button className="btn inline-flex items-center gap-2 whitespace-nowrap" onClick={() => fileInput.current?.click()}>
            <Upload size={14} /> Datei hinzufuegen
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
            "mt-5 border border-dashed border-rule px-6 py-10 text-center text-sm text-muted",
            dragActive && "bg-bg border-accent",
          )}
          onDragOver={(e) => { e.preventDefault(); setDragActive(true); }}
          onDragLeave={() => setDragActive(false)}
          onDrop={(e) => {
            e.preventDefault();
            setDragActive(false);
            handleFiles(e.dataTransfer.files);
          }}
        >
          Dateien hier ablegen oder oben auf „Datei hinzufuegen" klicken.
        </div>
      )}

      <ul className="mt-5 divide-y divide-rule-soft">
        {isLoading && <li className="py-4 text-quiet italic text-sm">Lade …</li>}
        {items && items.length === 0 && (
          <li className="py-6 text-quiet italic text-sm">Noch keine Anhaenge.</li>
        )}
        {items?.map((a: Attachment) => (
          <li key={a.id} className="grid grid-cols-[auto_1fr_auto_auto] items-center gap-4 py-3">
            <FileText size={18} className="text-muted" />
            <div>
              <a
                href={attachmentDownloadUrl(instanceId, a.id)}
                className="text-ink hover:text-accent text-[14px]"
                download={a.filename}
              >
                {a.filename}
              </a>
              <div className="font-mono text-[11px] text-quiet mt-0.5">
                {(a.size_bytes / 1024).toFixed(1)} KB ·  SHA-256 {a.sha256.slice(0, 12)}…
                ·  hochgeladen von {a.uploaded_by} am {formatDate(a.uploaded_at)}
              </div>
            </div>
            <a
              href={attachmentDownloadUrl(instanceId, a.id)}
              download={a.filename}
              className="text-muted hover:text-accent inline-flex items-center gap-1 font-mono text-[11px] uppercase tracking-wider"
              title="Herunterladen"
            >
              <Download size={14} />
            </a>
            {!readOnly && (
              <button
                onClick={() => {
                  if (confirm(`Anhang "${a.filename}" wirklich loeschen?`)) deleteMut.mutate(a.id);
                }}
                disabled={deleteMut.isPending}
                className="text-muted hover:text-bad inline-flex items-center gap-1"
                title="Loeschen"
              >
                <Trash2 size={14} />
              </button>
            )}
          </li>
        ))}
      </ul>
    </div>
  );
}
