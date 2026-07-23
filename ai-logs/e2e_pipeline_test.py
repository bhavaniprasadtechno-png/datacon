#!/usr/bin/env python3
"""E2E test for the multi-agent pipeline: retriever → router → analysts →
validator → responder, running against a live FastAPI ai/ service with a
real TOGETHER_API_KEY."""
import json
import re
import sys
import time
import urllib.request

BASE = "http://localhost:8100"
HEADERS = {"Content-Type": "application/json", "X-Internal-Auth": "dev-internal-token"}

CTX = {
    "revenueHistory": [3.1, 3.3, 3.6, 3.5, 3.8, 4.1, 4.3, 4.4, 4.7, 4.9,
                       5.0, 4.8, 5.2, 5.5, 5.7, 5.6, 6.0, 6.2],
    "regionRevenue": {
        "current": [{"region": "NA", "revenue": 2.8}, {"region": "EMEA", "revenue": 2.1},
                    {"region": "APAC", "revenue": 1.0}, {"region": "LATAM", "revenue": 0.3}],
        "previous": [{"region": "NA", "revenue": 2.6}, {"region": "EMEA", "revenue": 2.2},
                     {"region": "APAC", "revenue": 0.9}, {"region": "LATAM", "revenue": 0.4}],
    },
    "ticketDaily": [
        {"date": "2024-01-01", "region": "NA", "count": 5},
        {"date": "2024-01-05", "region": "NA", "count": 22},
        {"date": "2024-01-06", "region": "EMEA", "count": 6},
    ],
    "churnSnapshot": {"churnPct": 4.8, "prevChurnPct": 4.1, "atRiskAccounts": 17},
    "topIncidentTitle": "Q4 outage report",
    "model": "Holt-Winters", "horizonMonths": 6,
}


def stream_chat(message, timeout=60):
    body = json.dumps({"message": message, "context": CTX,
                       "model": "Qwen/Qwen3.7-Plus"}).encode()
    req = urllib.request.Request(f"{BASE}/internal/chat/stream", data=body,
                                 headers=HEADERS, method="POST")
    events = []
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        buf = ""
        for chunk in resp:
            buf += chunk.decode("utf-8", errors="replace")
            while "\n\n" in buf:
                frame, buf = buf.split("\n\n", 1)
                em = re.search(r"^event: (.+)$", frame, re.M)
                dm = re.search(r"^data: (.+)$", frame, re.M)
                if em and dm:
                    events.append((em.group(1), json.loads(dm.group(1))))
    return events


def summarise(events):
    text = "".join(d["text"] for e, d in events if e == "agent_delta")
    done = [d for e, d in events if e == "agent_done"]
    retr = next((d for e, d in events if e == "retriever_done"), None)
    vald = next((d for e, d in events if e == "validator_done"), None)
    intents = next((d["intents"] for e, d in events if e == "agents"), None)
    return {"text": text, "done": done, "retriever": retr, "validator": vald, "intents": intents}


def run(label, question):
    print(f"\n=== {label} ===")
    print(f"Q: {question}")
    t0 = time.monotonic()
    events = stream_chat(question)
    dt = time.monotonic() - t0
    s = summarise(events)
    print(f"latency: {dt:.2f}s  primary_intent: {s['intents']}")
    print(f"retriever: db_fields={s['retriever']['db_field_count']} "
          f"docs={s['retriever']['doc_chunk_count']} sources={s['retriever']['sources'][:3]}")
    print(f"validator: {json.dumps({k: (len(v) if isinstance(v, list) else v) for k, v in s['validator'].items()})}")
    if s["done"]:
        d = s["done"][0]
        print(f"analysts_selected: {d['payload']['details']['intents_selected']}")
        print(f"\nRESPONDER (bubble text):\n  {d['text'][:800].replace(chr(10), chr(10)+'  ')}")
    return dt, s


def main():
    _, warm = run("WARMUP", "hello there")

    _, s1 = run("DESCRIPTIVE (revenue snapshot)", "How are we doing this quarter?")
    _, s2 = run("DIAGNOSTIC + PRESCRIPTIVE (multi)", "Why did tickets spike and what should we do?")
    _, s3 = run("PREDICTIVE (forecast)", "Forecast our revenue for the next 6 months.")

    # Structural assertions
    for label, s in [("descriptive", s1), ("multi", s2), ("predictive", s3)]:
        assert s["done"], f"{label} missing agent_done"
        d = s["done"][0]
        details = d["payload"]["details"]
        assert "retriever" in details, f"{label} missing retriever details"
        assert "analysts" in details, f"{label} missing analysts details"
        assert "validator" in details, f"{label} missing validator details"
        assert details["retriever"]["sources"], f"{label} retriever has no sources"
        # Bubble text must not be empty
        assert d["text"].strip(), f"{label} bubble text empty"

    # Content assertions: source citation should appear when LLM is up
    combined = s1["text"] + s2["text"] + s3["text"]
    assert any(marker in combined.lower() for marker in ("source", "revenue_metrics", "region_revenue", "db:", "doc:")), \
        f"no source citations found in any answer: {combined[:400]!r}"

    # Predictive should mention forecast numbers
    assert any(t in s3["text"] for t in ("7.2", "7.20", "6.6", "16.1", "16.18", "Holt", "MAPE", "confidence")), \
        f"predictive answer missing forecast numbers: {s3['text'][:300]!r}"

    print("\n===============================")
    print("PIPELINE E2E TESTS PASSED ✓")
    print("===============================")


if __name__ == "__main__":
    try:
        main()
    except AssertionError as e:
        print(f"\nFAIL: {e}", file=sys.stderr)
        sys.exit(1)
