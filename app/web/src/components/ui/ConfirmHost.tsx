import { useConfirmStore } from "../../stores/useConfirmStore";
import { Modal } from "./Modal";
import { Button } from "./Button";

export function ConfirmHost() {
  const pending = useConfirmStore((state) => state.pending);
  const resolve = useConfirmStore((state) => state.resolve);

  return (
    <Modal open={!!pending} onClose={() => resolve(false)} width={400} z={60}>
      {pending && (
        <>
          <div style={{ fontSize: 16, fontWeight: 800, marginBottom: 8 }}>{pending.title}</div>
          <div style={{ fontSize: 13, color: "#71768a", marginBottom: 20, lineHeight: 1.5 }}>{pending.body}</div>
          <div style={{ display: "flex", justifyContent: "flex-end", gap: 10 }}>
            <Button variant="secondary" onClick={() => resolve(false)}>
              Cancel
            </Button>
            <Button variant={pending.tone === "danger" ? "danger" : "primary"} onClick={() => resolve(true)}>
              {pending.label}
            </Button>
          </div>
        </>
      )}
    </Modal>
  );
}
