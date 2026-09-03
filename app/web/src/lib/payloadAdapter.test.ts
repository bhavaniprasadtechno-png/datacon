import { describe, expect, it } from "vitest";
import { adaptPayload } from "./payloadAdapter";

describe("adaptPayload", () => {
  it("preserves citations and correlation from a structured-shape payload that also carries escape-hatch fields", () => {
    const payload = {
      summary: { text: "Billing has the most tickets.", confidence: "high" },
      metrics: [{ id: "total_tickets", label: "Total Tickets", value: 6, format: "number" }],
      insights: [],
      visualizations: [],
      tables: [],
      sources: [],
      citations: [
        { id: 1, documentTitle: "Incident Report", filename: "incident.pdf", chunkIndex: 0, snippet: "..." },
      ],
      correlation: "spike ↔ Incident Report",
    };

    const adapted = adaptPayload(payload, "fallback");

    expect(adapted.citations).toEqual(payload.citations);
    expect(adapted.correlation).toBe("spike ↔ Incident Report");
  });

  it("still returns empty escape-hatch fields for a pure structured-shape payload with none present", () => {
    const payload = {
      summary: { text: "You have 4 customers.", confidence: "high" },
      metrics: [],
      insights: [],
      visualizations: [],
      tables: [],
      sources: [],
    };

    const adapted = adaptPayload(payload, "fallback");

    expect(adapted.citations).toEqual([]);
    expect(adapted.correlation).toBeNull();
  });
});
