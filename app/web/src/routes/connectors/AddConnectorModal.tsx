import { useState } from "react";
import { ENGINE_LIST, ENGINE_FIELDS, SYNC_SCHEDULE_OPTIONS, allFields, type ConnectorEngineId, type EngineField } from "@datacon/shared-types";
import { Modal, ModalHeader } from "../../components/ui/Modal";
import { Button } from "../../components/ui/Button";
import { TYPE_STYLE } from "../../lib/connectorMeta";
import { useCreateConnector, useTestDraftConnector } from "../../api/connectors";
import { useToast } from "../../stores/useToastStore";
import { apiErrorMessage } from "../../api/client";

type Step = "pick" | "config";

export function AddConnectorModal({ open, onClose }: { open: boolean; onClose: () => void }) {
  const [step, setStep] = useState<Step>("pick");
  const [engine, setEngine] = useState<ConnectorEngineId | null>(null);
  const [name, setName] = useState("");
  const [fields, setFields] = useState<Record<string, string>>({});
  const [syncInterval, setSyncInterval] = useState(SYNC_SCHEDULE_OPTIONS[0]);
  const [testState, setTestState] = useState<"idle" | "testing" | "pass" | "fail">("idle");
  const [testMsg, setTestMsg] = useState("");

  const testDraft = useTestDraftConnector();
  const createConnector = useCreateConnector();
  const { addToast } = useToast();

  const reset = () => {
    setStep("pick");
    setEngine(null);
    setName("");
    setFields({});
    setSyncInterval(SYNC_SCHEDULE_OPTIONS[0]);
    setTestState("idle");
    setTestMsg("");
  };

  const close = () => {
    reset();
    onClose();
  };

  const pickEngine = (id: ConnectorEngineId) => {
    setEngine(id);
    const defaults: Record<string, string> = {};
    for (const f of allFields(id)) {
      if (f.default) defaults[f.key] = f.default;
    }
    setFields(defaults);
    setName(ENGINE_FIELDS[id].name);
    setStep("config");
  };

  const setField = (key: string, value: string) => {
    setFields((prev) => ({ ...prev, [key]: value }));
    setTestState("idle");
  };

  const runTest = async () => {
    if (!engine) return;
    setTestState("testing");
    try {
      const res = await testDraft.mutateAsync({ engine, fields });
      setTestState(res.ok ? "pass" : "fail");
      setTestMsg(res.message);
    } catch (err) {
      setTestState("fail");
      setTestMsg(apiErrorMessage(err, "Couldn't reach the connection test service."));
    }
  };

  const save = async () => {
    if (!engine || testState !== "pass") return;
    try {
      await createConnector.mutateAsync({ name, engine, fields, syncInterval });
      addToast({ icon: "🔌", accent: "var(--ac)", title: "Connector added", desc: `${name} is discovering tables…` });
      close();
    } catch (err) {
      addToast({ icon: "⚠️", accent: "#e2603f", title: "Couldn't add connector", desc: apiErrorMessage(err) });
    }
  };

  const def = engine ? ENGINE_FIELDS[engine] : null;

  return (
    <Modal open={open} onClose={close} width={520}>
      <ModalHeader title="Add data connector" onClose={close} />

      {step === "pick" && (
        <>
          <div style={{ fontSize: 12.5, color: "#71768a", marginBottom: 14 }}>Choose the engine you want to connect — you'll configure it next.</div>
          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 10, maxHeight: "56vh", overflowY: "auto" }}>
            {ENGINE_LIST.map((e) => {
              const style = TYPE_STYLE[e.id as ConnectorEngineId];
              return (
                <button
                  key={e.id}
                  onClick={() => pickEngine(e.id as ConnectorEngineId)}
                  style={{ display: "flex", gap: 10, textAlign: "left", padding: 12, borderRadius: 12, border: "1px solid #e2e4ee", background: "#fff" }}
                >
                  <div style={{ width: 30, height: 30, borderRadius: 9, background: style.bg, color: style.color, display: "flex", alignItems: "center", justifyContent: "center", fontWeight: 800, fontSize: 13, flexShrink: 0 }}>
                    {style.letter}
                  </div>
                  <div>
                    <div style={{ fontSize: 12.5, fontWeight: 700 }}>{e.name}</div>
                    <div style={{ fontSize: 10.5, color: "#9499ad", marginTop: 2 }}>{e.description}</div>
                  </div>
                </button>
              );
            })}
          </div>
        </>
      )}

      {step === "config" && engine && def && (
        <>
          <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 14 }}>
            <div style={{ width: 26, height: 26, borderRadius: 8, background: TYPE_STYLE[engine].bg, color: TYPE_STYLE[engine].color, display: "flex", alignItems: "center", justifyContent: "center", fontWeight: 800, fontSize: 11 }}>
              {TYPE_STYLE[engine].letter}
            </div>
            <div style={{ fontSize: 13, fontWeight: 700 }}>{def.name}</div>
            <button onClick={() => setStep("pick")} style={{ marginLeft: "auto", fontSize: 12, color: "var(--ac)", fontWeight: 700 }}>
              Change
            </button>
          </div>

          <FormField label="CONNECTOR NAME">
            <input value={name} onChange={(e) => setName(e.target.value)} placeholder={def.name} style={fieldInputStyle()} />
          </FormField>

          <DynamicField field={def.primary} value={fields[def.primary.key] ?? ""} onChange={(v) => setField(def.primary.key, v)} />
          {def.secondary.map((f) => (
            <DynamicField key={f.key} field={f} value={fields[f.key] ?? ""} onChange={(v) => setField(f.key, v)} />
          ))}

          <FormField label="SYNC SCHEDULE">
            <select value={syncInterval} onChange={(e) => setSyncInterval(e.target.value)} style={fieldInputStyle(false)}>
              {SYNC_SCHEDULE_OPTIONS.map((o) => (
                <option key={o} value={o}>
                  {o}
                </option>
              ))}
            </select>
          </FormField>

          {testState === "testing" && <TestBanner tone="pending">Testing connection…</TestBanner>}
          {testState === "pass" && <TestBanner tone="pass">✓ {testMsg || "Connection succeeded"}</TestBanner>}
          {testState === "fail" && <TestBanner tone="fail">✕ {testMsg || "Couldn't connect — fill in the required fields to test"}</TestBanner>}

          <div style={{ display: "flex", justifyContent: "flex-end", gap: 10, marginTop: 18 }}>
            <Button variant="secondary" onClick={close}>
              Cancel
            </Button>
            <Button variant="secondary" onClick={runTest} disabled={testState === "testing"}>
              Test connection
            </Button>
            <Button variant="primary" disabled={testState !== "pass" || createConnector.isPending} onClick={save}>
              Connect & discover
            </Button>
          </div>
        </>
      )}
    </Modal>
  );
}

function DynamicField({ field, value, onChange }: { field: EngineField; value: string; onChange: (v: string) => void }) {
  const mono = field.kind !== "select" && field.type !== "password";
  return (
    <FormField label={field.label.toUpperCase()} required={field.required} help={field.help}>
      {field.kind === "select" ? (
        <select value={value || field.default || ""} onChange={(e) => onChange(e.target.value)} style={fieldInputStyle(false)}>
          {field.options?.map((o) => (
            <option key={o} value={o}>
              {o}
            </option>
          ))}
        </select>
      ) : field.kind === "textarea" ? (
        <textarea value={value} onChange={(e) => onChange(e.target.value)} placeholder={field.placeholder} rows={4} style={{ ...fieldInputStyle(true), resize: "vertical" }} />
      ) : (
        <input
          type={field.type === "password" ? "password" : "text"}
          value={value}
          onChange={(e) => onChange(e.target.value)}
          placeholder={field.placeholder}
          style={fieldInputStyle(mono)}
        />
      )}
    </FormField>
  );
}

function FormField({ label, required, help, children }: { label: string; required?: boolean; help?: string; children: React.ReactNode }) {
  return (
    <div style={{ marginBottom: help ? 6 : 15 }}>
      <label style={{ display: "block", font: "600 10.5px 'IBM Plex Mono',monospace", letterSpacing: ".06em", color: "#5a5f72", marginBottom: 6 }}>
        {label} {required && <span style={{ color: "#e2603f" }}>*</span>}
      </label>
      {children}
      {help && <div style={{ fontSize: 11, color: "#9499ad", marginTop: 4, marginBottom: 9 }}>{help}</div>}
    </div>
  );
}

function fieldInputStyle(mono = true): React.CSSProperties {
  return {
    width: "100%",
    padding: "9px 11px",
    border: "1px solid #e2e4ee",
    borderRadius: 9,
    fontSize: 12.5,
    fontFamily: mono ? "'IBM Plex Mono',monospace" : "inherit",
  };
}

function TestBanner({ tone, children }: { tone: "pending" | "pass" | "fail"; children: React.ReactNode }) {
  const styles = {
    pending: { bg: "#f5f6fb", color: "#71768a" },
    pass: { bg: "#e6f7ef", color: "#0f8a5c" },
    fail: { bg: "#fdeee9", color: "#c0392b" },
  }[tone];
  return (
    <div style={{ background: styles.bg, color: styles.color, borderRadius: 9, padding: "8px 11px", fontSize: 12, fontWeight: 600, marginBottom: 8 }}>{children}</div>
  );
}
