import type { ReactNode } from "react";
import { Dialog, DialogContent, DialogTitle, DialogDescription } from "../shadcn-ui/ui/dialog";

interface Props {
  open: boolean;
  onClose: () => void;
  width?: number;
  children: ReactNode;
  z?: number;
}

export function Modal({ open, onClose, children, width = 440 }: Props) {
  return (
    <Dialog open={open} onOpenChange={(val) => { if (!val) onClose(); }}>
      <DialogContent 
        className="max-h-[90vh] overflow-y-auto rounded-xl p-5 shadow-lg border-border bg-background"
        style={{ maxWidth: `min(${width}px, 92vw)` }}
        showCloseButton={false}
      >
        <div className="sr-only">
          <DialogTitle>Dialog Window</DialogTitle>
          <DialogDescription>Content modal details</DialogDescription>
        </div>
        {children}
      </DialogContent>
    </Dialog>
  );
}

export function ModalHeader({ title, onClose }: { title: string; onClose: () => void }) {
  return (
    <div className="flex items-center justify-between mb-4">
      <div className="text-[17px] font-extrabold text-foreground">{title}</div>
      <button onClick={onClose} className="text-[16px] text-muted-foreground hover:text-foreground">
        ✕
      </button>
    </div>
  );
}
