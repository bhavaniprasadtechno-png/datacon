import { createContext, useCallback, useContext, useRef, useState, type ReactNode } from "react";

export interface ToastSpec {
  icon: ReactNode;
  accent: string;
  title: string;
  desc: string;
}

interface Toast extends ToastSpec {
  id: number;
}

interface ToastContextValue {
  toasts: Toast[];
  addToast: (t: ToastSpec) => void;
  dismiss: (id: number) => void;
}

const ToastContext = createContext<ToastContextValue | null>(null);

const AUTO_DISMISS_MS = 5200;

export function ToastProvider({ children }: { children: ReactNode }) {
  const [toasts, setToasts] = useState<Toast[]>([]);
  const seq = useRef(1);

  const dismiss = useCallback((id: number) => {
    setToasts((prev) => prev.filter((t) => t.id !== id));
  }, []);

  const addToast = useCallback(
    (t: ToastSpec) => {
      const id = seq.current++;
      setToasts((prev) => [...prev, { ...t, id }]);
      setTimeout(() => dismiss(id), AUTO_DISMISS_MS);
    },
    [dismiss],
  );

  return <ToastContext.Provider value={{ toasts, addToast, dismiss }}>{children}</ToastContext.Provider>;
}

export function useToast() {
  const ctx = useContext(ToastContext);
  if (!ctx) throw new Error("useToast must be used within ToastProvider");
  return ctx;
}
