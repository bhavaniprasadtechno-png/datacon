import { create } from "zustand";

export interface ConfirmSpec {
  title: string;
  body: string;
  label: string;
  tone: "primary" | "danger";
}

interface PendingConfirm extends ConfirmSpec {
  resolve: (ok: boolean) => void;
}

interface ConfirmState {
  pending: PendingConfirm | null;
  confirm: (spec: ConfirmSpec) => Promise<boolean>;
  resolve: (ok: boolean) => void;
}

export const useConfirmStore = create<ConfirmState>((set, get) => ({
  pending: null,
  confirm: (spec) => {
    return new Promise<boolean>((resolve) => {
      set({ pending: { ...spec, resolve } });
    });
  },
  resolve: (ok) => {
    const pending = get().pending;
    if (pending) {
      pending.resolve(ok);
    }
    set({ pending: null });
  },
}));

export function useConfirm() {
  const confirm = useConfirmStore((state) => state.confirm);
  return confirm;
}
