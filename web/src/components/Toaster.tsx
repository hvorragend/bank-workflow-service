import { createContext, useCallback, useContext, useState } from "react";
import type { ReactNode } from "react";
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

  return (
    <ToastCtx.Provider value={{ show }}>
      {children}
      <div className="fixed bottom-8 right-8 z-50 flex flex-col gap-2">
        {toasts.map((t) => (
          <div
            key={t.id}
            className={cn(
              "max-w-md px-5 py-4 bg-ink text-paper text-sm border-l-2 animate-slidein",
              t.variant === "error" && "border-l-bad",
              t.variant === "success" && "border-l-ok",
              t.variant === "info" && "border-l-neutral",
            )}
          >
            {t.message}
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
