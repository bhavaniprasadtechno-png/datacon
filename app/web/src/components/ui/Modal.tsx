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
        className="block max-h-[90vh] gap-0 overflow-y-auto rounded-xl p-5 pt-0 shadow-lg border-border bg-background"
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
    <div className="sticky top-0 z-10 mb-4 flex items-center justify-between bg-background pt-5">
      <div className="text-[17px] font-extrabold text-foreground">{title}</div>
      <button onClick={onClose} className="text-[16px] text-muted-foreground hover:text-foreground">
        ✕
      </button>
    </div>
  );
}

/** Sticky action bar pinned to the bottom of the modal's (single) scroll container. */
export function ModalFooter({ children }: { children: ReactNode }) {
  return (
    <div className="sticky bottom-0 z-10 -mb-5 bg-background pb-5">
      {children}
    </div>
  );
}
