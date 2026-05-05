import { createContext, useCallback, useContext, useState } from "react";
import type { ReactNode } from "react";
import { CheckCircle2, Info, X, XCircle } from "lucide-react";

import { cn } from "@/lib/utils";

type Variant = "success" | "error" | "info";
interface Toast {
  id: number;
  message: string;
  variant: Variant;
}

interface Ctx {
  show: (message: string, variant?: Variant) => void;
}

const ToastCtx = createContext<Ctx | null>(null);

export function ToasterProvider({ children }: { children: ReactNode }) {
  const [toasts, setToasts] = useState<Toast[]>([]);

  const show = useCallback((message: string, variant: Variant = "success") => {
    const id = Date.now() + Math.random();
    setToasts((t) => [...t, { id, message, variant }]);
    setTimeout(() => setToasts((t) => t.filter((x) => x.id !== id)), 4000);
  }, []);

  function dismiss(id: number) {
    setToasts((t) => t.filter((x) => x.id !== id));
  }

  return (
    <ToastCtx.Provider value={{ show }}>
      {children}
      <div className="fixed inset-x-3 bottom-4 sm:inset-x-auto sm:bottom-8 sm:right-8 z-50 flex flex-col gap-2 pointer-events-none">
        {toasts.map((t) => (
          <div
            key={t.id}
            className={cn(
              "pointer-events-auto flex items-start gap-3 max-w-md sm:min-w-[320px] px-4 sm:px-5 py-3 sm:py-4",
              "rounded-lg shadow-pop bg-paper text-ink text-sm border-l-[3px] animate-slidein",
              t.variant === "error"   && "border-l-bad",
              t.variant === "success" && "border-l-ok",
              t.variant === "info"    && "border-l-accent",
            )}
            role={t.variant === "error" ? "alert" : "status"}
          >
            <span
              className={cn(
                "mt-0.5 shrink-0",
                t.variant === "error"   && "text-bad",
                t.variant === "success" && "text-ok",
                t.variant === "info"    && "text-accent",
              )}
              aria-hidden
            >
              {t.variant === "error" ? <XCircle size={18} />
                : t.variant === "info" ? <Info size={18} />
                : <CheckCircle2 size={18} />}
            </span>
            <div className="flex-1 leading-snug">{t.message}</div>
            <button
              onClick={() => dismiss(t.id)}
              className="text-quiet hover:text-ink shrink-0 -mr-1"
              aria-label="Schliessen"
            >
              <X size={14} />
            </button>
          </div>
        ))}
      </div>
    </ToastCtx.Provider>
  );
}

export function useToast(): Ctx {
  const ctx = useContext(ToastCtx);
  if (!ctx) throw new Error("useToast braucht <ToasterProvider>.");
  return ctx;
}
