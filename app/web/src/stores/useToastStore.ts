import { create } from "zustand";
import type { ReactNode } from "react";

export interface ToastSpec {
  icon: ReactNode;
  accent: string;
  title: string;
  desc: string;
}

export interface Toast extends ToastSpec {
  id: number;
}

interface ToastState {
  toasts: Toast[];
  addToast: (spec: ToastSpec) => void;
  dismiss: (id: number) => void;
}

let seq = 1;
const AUTO_DISMISS_MS = 5200;

export const useToastStore = create<ToastState>((set, get) => ({
  toasts: [],
  addToast: (spec) => {
    const id = seq++;
    set((state) => ({ toasts: [...state.toasts, { ...spec, id }] }));
    setTimeout(() => get().dismiss(id), AUTO_DISMISS_MS);
  },
  dismiss: (id) => {
    set((state) => ({ toasts: state.toasts.filter((t) => t.id !== id) }));
  },
}));

export function useToast() {
  const toasts = useToastStore((state) => state.toasts);
  const addToast = useToastStore((state) => state.addToast);
  const dismiss = useToastStore((state) => state.dismiss);

  return { toasts, addToast, dismiss };
}
