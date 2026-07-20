import { useConfirmStore } from "../../stores/useConfirmStore";
import {
  AlertDialog,
  AlertDialogContent,
  AlertDialogHeader,
  AlertDialogTitle,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogAction,
  AlertDialogCancel,
} from "./AlertDialog";

export function ConfirmHost() {
  const pending = useConfirmStore((state) => state.pending);
  const resolve = useConfirmStore((state) => state.resolve);

  return (
    <AlertDialog open={!!pending} onOpenChange={(open) => { if (!open) resolve(false); }}>
      {pending && (
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>{pending.title}</AlertDialogTitle>
            <AlertDialogDescription>{pending.body}</AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel onClick={() => resolve(false)}>
              Cancel
            </AlertDialogCancel>
            <AlertDialogAction
              variant={pending.tone === "danger" ? "danger" : "primary"}
              onClick={() => resolve(true)}
            >
              {pending.label}
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      )}
    </AlertDialog>
  );
}
