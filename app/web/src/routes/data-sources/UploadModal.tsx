import { useRef, useState } from "react";
import { Modal } from "../../components/ui/Modal";
import { Button } from "../../components/ui/Button";
import { useUploadDataSource } from "../../api/documents";
import { useToast } from "../../stores/useToastStore";
import { apiErrorMessage } from "../../api/client";

type State = "idle" | "uploading" | "error";

export function UploadModal({ open, onClose }: { open: boolean; onClose: () => void }) {
  const [file, setFile] = useState<File | null>(null);
  const [state, setState] = useState<State>("idle");
  const [pct, setPct] = useState(0);
  const [stage, setStage] = useState("");
  const [errorMsg, setErrorMsg] = useState("");
  const inputRef = useRef<HTMLInputElement>(null);
  const upload = useUploadDataSource();
  const { addToast } = useToast();

  const reset = () => {
    setFile(null);
    setState("idle");
    setPct(0);
    setStage("");
    setErrorMsg("");
  };

  const close = () => {
    reset();
    onClose();
  };

  const doUpload = async () => {
    if (!file) return;
    setState("uploading");
    setStage("Uploading…");
    setPct(0);
    try {
      const result = await upload.mutateAsync({
        file,
        onProgress: (p) => {
          setPct(p);
          if (p >= 100) setStage("Chunking & embedding in ChromaDB…");
        },
      });
      if (result.status === "FAILED") {
        setState("error");
        setErrorMsg(result.failureMsg ?? "Upload failed.");
        return;
      }
      addToast({
        icon: "📄",
        accent: "var(--ac)",
        title: `${file.name} uploaded`,
        desc: result.type === "CSV" ? `Parsed ${result.rowCount} rows` : `Indexed ${result.chunkCount} chunk(s)`,
      });
      close();
    } catch (err) {
      setState("error");
      setErrorMsg(apiErrorMessage(err, "Upload failed. Please try again."));
    }
  };

  return (
    <Modal open={open} onClose={close}>
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 6 }}>
        <div style={{ fontSize: 18, fontWeight: 800 }}>Upload a data source</div>
        <button onClick={close} style={{ fontSize: 16, color: "#9499ad" }}>
          ✕
        </button>
      </div>
      <div style={{ fontSize: 12.5, color: "#9499ad", marginBottom: 18 }}>
        Accepts CSV (structured, feeds the Descriptive agent) or PDF / TXT / MD (unstructured, feeds the RAG pipeline). Max 10 MB.
      </div>

      <input
        ref={inputRef}
        type="file"
        accept=".pdf,.csv,.txt,.md"
        style={{ display: "none" }}
        onChange={(e) => {
          setFile(e.target.files?.[0] ?? null);
          setState("idle");
        }}
      />

      {state !== "error" && (
        <>
          <div style={{ display: "flex", alignItems: "center", gap: 12, border: "1px dashed #d4d7e2", borderRadius: 12, padding: "14px 16px", marginBottom: 18 }}>
            <Button variant="secondary" onClick={() => inputRef.current?.click()} disabled={state === "uploading"}>
              Choose File
            </Button>
            <span style={{ fontSize: 12.5, color: file ? "#1a1d29" : "#9499ad" }}>{file ? file.name : "No file chosen"}</span>
          </div>

          {state === "uploading" && (
            <div style={{ marginBottom: 18 }}>
              <div style={{ display: "flex", justifyContent: "space-between", fontSize: 12, marginBottom: 6 }}>
                <span style={{ fontFamily: "'IBM Plex Mono',monospace" }}>{file?.name}</span>
                <span style={{ color: "var(--ac)", fontWeight: 700 }}>{pct}%</span>
              </div>
              <div style={{ height: 6, background: "#eef0f6", borderRadius: 4, overflow: "hidden" }}>
                <div style={{ width: `${pct}%`, height: "100%", background: "linear-gradient(90deg,var(--ac),#2bb8c4)", transition: "width .2s" }} />
              </div>
              <div style={{ fontSize: 11.5, color: "#9499ad", marginTop: 6 }}>{stage}</div>
            </div>
          )}

          <div style={{ display: "flex", justifyContent: "flex-end", gap: 10 }}>
            <Button variant="secondary" onClick={close} disabled={state === "uploading"}>
              Cancel
            </Button>
            <Button variant="primary" disabled={!file || state === "uploading"} onClick={doUpload}>
              Upload
            </Button>
          </div>
        </>
      )}

      {state === "error" && (
        <>
          <div style={{ background: "#fdeee9", border: "1px solid #f6cfc2", borderRadius: 10, padding: 12, marginBottom: 18 }}>
            <div style={{ fontSize: 13, fontWeight: 700, color: "#c0392b", marginBottom: 4 }}>⚠ Upload rejected</div>
            <div style={{ fontSize: 12.5, color: "#8a3226" }}>{errorMsg}</div>
          </div>
          <div style={{ display: "flex", justifyContent: "flex-end", gap: 10 }}>
            <Button variant="secondary" onClick={close}>
              Cancel
            </Button>
            <Button variant="primary" onClick={() => inputRef.current?.click()}>
              Choose another
            </Button>
          </div>
        </>
      )}
    </Modal>
  );
}
