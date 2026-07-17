import { useTheme } from "../../stores/useThemeStore";
import { useToast } from "../../stores/useToastStore";
import { THEME_PRESETS } from "@datacon/shared-types";
import { Button } from "../../components/ui/Button";

export function ThemesPage() {
  const { themeId, customAccent, setTheme, setCustomAccent } = useTheme();
  const { addToast } = useToast();

  const choosePreset = (id: (typeof THEME_PRESETS)[number]) => {
    setTheme(id.id);
    addToast({ icon: "🎨", accent: id.ac, title: "Theme applied", desc: `${id.name} is now active` });
  };

  const applyCustom = () => {
    setCustomAccent(customAccent);
    addToast({ icon: "🎨", accent: customAccent, title: "Custom theme applied", desc: `Accent set to ${customAccent}` });
  };

  return (
    <div style={{ padding: 32, maxWidth: 1080, margin: "0 auto" }}>
      <h1 style={{ fontSize: 21, fontWeight: 800, margin: 0 }}>Themes</h1>
      <div style={{ fontSize: 12.5, color: "#9499ad", marginTop: 4, marginBottom: 24 }}>Choose a premium theme or craft your own accent</div>

      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 16, marginBottom: 16 }}>
        {THEME_PRESETS.map((preset) => {
          const active = themeId === preset.id;
          return (
            <button
              key={preset.id}
              onClick={() => choosePreset(preset)}
              style={{
                textAlign: "left",
                background: "#fff",
                borderRadius: 16,
                border: `2px solid ${active ? preset.ac : "#e9eaf2"}`,
                padding: 18,
              }}
            >
              <div style={{ display: "flex", alignItems: "center", gap: 12, marginBottom: 10 }}>
                <div style={{ width: 52, height: 52, borderRadius: 16, background: `linear-gradient(135deg,${preset.ac},${preset.ac2})`, flexShrink: 0 }} />
                <div>
                  <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                    <span style={{ fontSize: 14.5, fontWeight: 800 }}>{preset.name}</span>
                    {active && <span style={{ fontSize: 9.5, fontWeight: 700, color: "#fff", background: preset.ac, padding: "2px 8px", borderRadius: 20 }}>ACTIVE</span>}
                  </div>
                  <div style={{ fontSize: 12, color: "#9499ad", marginTop: 2 }}>{preset.description}</div>
                </div>
              </div>
              <div style={{ display: "flex", gap: 6 }}>
                <div style={{ flex: 2, height: 8, borderRadius: 4, background: preset.ac }} />
                <div style={{ flex: 2, height: 8, borderRadius: 4, background: preset.ac2 }} />
                <div style={{ flex: 1, height: 8, borderRadius: 4, background: preset.tint }} />
              </div>
            </button>
          );
        })}
      </div>

      <div style={{ background: "#fff", borderRadius: 16, border: `2px solid ${themeId === "custom" ? customAccent : "#e9eaf2"}`, padding: 18, marginBottom: 16 }}>
        <div style={{ display: "flex", alignItems: "center", gap: 14 }}>
          <div style={{ position: "relative", width: 52, height: 52, borderRadius: 16, background: `linear-gradient(135deg,${customAccent},${customAccent})`, display: "flex", alignItems: "center", justifyContent: "center", fontSize: 20, flexShrink: 0 }}>
            🎨
            <input
              type="color"
              value={customAccent}
              onChange={(e) => setCustomAccent(e.target.value)}
              style={{ position: "absolute", inset: 0, opacity: 0, cursor: "pointer" }}
            />
          </div>
          <div style={{ flex: 1 }}>
            <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
              <span style={{ fontSize: 14.5, fontWeight: 800 }}>Custom</span>
              {themeId === "custom" && <span style={{ fontSize: 9.5, fontWeight: 700, color: "#fff", background: customAccent, padding: "2px 8px", borderRadius: 20 }}>ACTIVE</span>}
            </div>
            <div style={{ fontSize: 12, color: "#9499ad", marginTop: 2 }}>
              Pick any accent · <span style={{ fontFamily: "'IBM Plex Mono',monospace" }}>{customAccent}</span>
            </div>
          </div>
          <Button variant="primary" onClick={applyCustom}>
            Apply
          </Button>
        </div>
      </div>

      <div style={{ display: "flex", alignItems: "center", gap: 8, fontSize: 12, color: "#9499ad" }}>
        <span>✨</span>
        Themes apply instantly across the whole workspace and persist while you explore.
      </div>
    </div>
  );
}
