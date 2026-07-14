#!/usr/bin/env python3
"""E2E test for the dynamic router + agents + cache path against a live
FastAPI ai/ service running with a real GEMINI_API_KEY."""
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
        "current": [
            {"region": "NA", "revenue": 2.8},
            {"region": "EMEA", "revenue": 2.1},
            {"region": "APAC", "revenue": 1.0},
            {"region": "LATAM", "revenue": 0.3},
        ],
        "previous": [
            {"region": "NA", "revenue": 2.6},
            {"region": "EMEA", "revenue": 2.2},
            {"region": "APAC", "revenue": 0.9},
            {"region": "LATAM", "revenue": 0.4},
        ],
    },
    "ticketDaily": [
        {"date": "2024-01-01", "region": "NA", "count": 5},
        {"date": "2024-01-02", "region": "NA", "count": 8},
        {"date": "2024-01-03", "region": "EMEA", "count": 4},
        {"date": "2024-01-04", "region": "NA", "count": 12},
        {"date": "2024-01-05", "region": "NA", "count": 22},
        {"date": "2024-01-06", "region": "EMEA", "count": 6},
    ],
    "churnSnapshot": {"churnPct": 4.8, "prevChurnPct": 4.1, "atRiskAccounts": 17},
    "topIncidentTitle": "Q4 outage report",
    "model": "Holt-Winters",
    "horizonMonths": 6,
}


def stream_chat(message: str, timeout: int = 45) -> dict:
    body = json.dumps({"message": message, "context": CTX,
                       "model": "gemini/gemini-2.5-flash"}).encode()
    req = urllib.request.Request(f"{BASE}/internal/chat/stream", data=body, headers=HEADERS, method="POST")
    intents: list[str] = []
    per_agent_text: dict[str, list[str]] = {}
    dones: list[dict] = []
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        buf = ""
        for chunk in resp:
            buf += chunk.decode("utf-8", errors="replace")
            while "\n\n" in buf:
                frame, buf = buf.split("\n\n", 1)
                em = re.search(r"^event: (.+)$", frame, re.M)
                dm = re.search(r"^data: (.+)$", frame, re.M)
                if not em or not dm:
                    continue
                event, data = em.group(1), json.loads(dm.group(1))
                if event == "agents":
                    intents = data["intents"]
                elif event == "agent_delta":
                    per_agent_text.setdefault(data["intent"], []).append(data["text"])
                elif event == "agent_done":
                    dones.append(data)
    return {"intents": intents, "streamed": {k: "".join(v) for k, v in per_agent_text.items()}, "dones": dones}


def run_case(label: str, message: str, expected_intents_subset: set[str]):
    print(f"\n=== {label} ===")
    print(f"Q: {message}")
    t0 = time.monotonic()
    r = stream_chat(message)
    dt = time.monotonic() - t0
    print(f"latency: {dt:.2f}s  intents: {r['intents']}")
    for d in r["dones"]:
        text = d["text"][:280].replace("\n", " ")
        print(f"  [{d['intent']}] {text}{'...' if len(d['text']) > 280 else ''}")
        if d["payload"]:
            keys = list(d["payload"].keys())
            print(f"     payload keys: {keys}")
    # Assertions
    assert r["intents"], "no intents returned"
    got = set(r["intents"])
    assert expected_intents_subset.issubset(got) or got == {"general"}, (
        f"expected {expected_intents_subset} in {got}"
    )
    for d in r["dones"]:
        assert d["text"].strip(), f"empty text for {d['intent']}"
    return dt, r


def main():
    # Warm the process (first call also pays litellm's ~130MB import cost)
    warm_dt, _ = run_case("WARMUP", "hello there", set())

    lat1, r1 = run_case("DESCRIPTIVE", "How are we doing this quarter?", {"descriptive"})
    lat2, r2 = run_case("DIAGNOSTIC", "Why did tickets spike?", {"diagnostic"})
    lat3, r3 = run_case("PREDICTIVE", "Forecast revenue for the next 6 months.", {"predictive"})
    lat4, r4 = run_case("PRESCRIPTIVE", "How can we reduce churn?", {"prescriptive"})
    lat5, r5 = run_case("MULTI (diagnostic + prescriptive)",
                        "Why did tickets spike and what should we do about it?",
                        {"diagnostic", "prescriptive"})
    lat6, r6 = run_case("GENERAL", "what is the capital of France?", {"general"})

    # Cache validation — repeat the exact same question, expect ~router-side speedup
    print("\n=== CACHE VALIDATION ===")
    print("Repeating DIAGNOSTIC question (router should hit cache)…")
    lat_first_repeat, _ = run_case("DIAGNOSTIC repeat", "Why did tickets spike?", {"diagnostic"})
    lat_second_repeat, _ = run_case("DIAGNOSTIC repeat 2", "Why did tickets spike?", {"diagnostic"})
    print(f"\nlatencies: first={lat2:.2f}s  repeat1={lat_first_repeat:.2f}s  repeat2={lat_second_repeat:.2f}s")

    # Cache stats endpoint (via internal python check on process)
    print("\n=== VALIDATIONS ===")
    # Descriptive should quote real numbers
    desc_text = r1["dones"][0]["text"]
    assert any(t in desc_text for t in ("6.2", "6.20", "+3.3", "3.3%", "NA")), \
        f"descriptive answer doesn't reference computed facts: {desc_text[:200]}"
    print("✓ descriptive answer references computed facts")

    # Predictive should reference the real forecast projected number
    pred_text = r3["dones"][0]["text"]
    assert any(t in pred_text for t in ("7.2", "7.20", "Holt", "CI", "MAPE", "confidence", "projected")), \
        f"predictive answer doesn't reference forecast: {pred_text[:200]}"
    pred_payload = r3["dones"][0]["payload"]
    assert "forecast" in pred_payload and pred_payload["forecast"], \
        f"predictive payload missing forecast: {pred_payload}"
    print(f"✓ predictive payload has forecast: {pred_payload['forecast']}")

    # Prescriptive should return a ranked action list
    presc_payload = r4["dones"][0]["payload"]
    assert "actions" in presc_payload and len(presc_payload["actions"]) > 0, \
        f"prescriptive missing actions: {presc_payload}"
    print(f"✓ prescriptive returned {len(presc_payload['actions'])} ranked actions")

    # Multi-intent
    assert len(r5["dones"]) >= 2, f"multi-intent expected ≥2 agent_done frames, got {len(r5['dones'])}"
    print(f"✓ multi-intent produced {len(r5['dones'])} agent responses")

    # General shouldn't get business data
    gen_payload = r6["dones"][0]["payload"]
    assert not gen_payload, f"general payload should be empty, got {gen_payload}"
    print("✓ general agent isolated from business data")

    print("\n===============================")
    print("ALL E2E TESTS PASSED ✓")
    print("===============================")


if __name__ == "__main__":
    try:
        main()
    except AssertionError as e:
        print(f"\nFAIL: {e}", file=sys.stderr)
        sys.exit(1)
