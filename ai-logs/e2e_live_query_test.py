#!/usr/bin/env python3
"""E2E test for the LIVE query pipeline: real Qwen/Qwen3.7-Plus plans a query
against a real SQLite database, retriever executes it, responder cites
the live result."""
import json
import os
import re
import sqlite3
import sys
import tempfile
import time
import urllib.request

BASE = "http://localhost:8100"
HEADERS = {"Content-Type": "application/json", "X-Internal-Auth": "dev-internal-token"}


def build_db():
    path = tempfile.mkstemp(suffix=".db")[1]
    c = sqlite3.connect(path)
    c.executescript("""
    CREATE TABLE orders (id INTEGER PRIMARY KEY, customer TEXT, region TEXT, amount REAL, status TEXT);
    INSERT INTO orders VALUES
        (1, 'Acme',    'NA',    1200.50, 'paid'),
        (2, 'Beta',    'EMEA',   340.00, 'paid'),
        (3, 'Gamma',   'NA',    2100.75, 'pending'),
        (4, 'Delta',   'APAC',   890.25, 'paid'),
        (5, 'Epsilon', 'LATAM',  115.00, 'refunded'),
        (6, 'Zeta',    'NA',    3300.00, 'paid'),
        (7, 'Theta',   'EMEA', 12000.00, 'paid');
    """)
    c.commit(); c.close()
    return path


def stream_chat(message, ctx, timeout=90):
    body = json.dumps({"message": message, "context": ctx,
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
    done = next((d for e, d in events if e == "agent_done"), None)
    retr = next((d for e, d in events if e == "retriever_done"), None)
    return {"text": text, "done": done, "retriever": retr}


def main():
    db_path = build_db()
    try:
        ctx = {
            # Pre-computed metrics blob (kept for backwards compat)
            "revenueHistory": [3.1, 3.3, 3.6, 4.1, 5.0, 6.2],
            "model": "Holt-Winters",
            "horizonMonths": 6,
            # NEW: catalog + connectors let the retriever run LIVE queries
            "catalog": [{
                "connector_id": "orders_db",
                "engine": "sqlite",
                "table": "orders",
                "columns": ["id", "customer", "region", "amount", "status"],
                "row_count": 7,
            }],
            "connectors": {"orders_db": {"config": {"path": db_path}, "secrets": {}}},
        }
        question = "Which paid customers have the highest order amounts?"
        print(f"Q: {question}")
        t0 = time.monotonic()
        events = stream_chat(question, ctx)
        dt = time.monotonic() - t0
        s = summarise(events)
        print(f"\nlatency: {dt:.2f}s")
        print(f"retriever_done: {json.dumps(s['retriever'], indent=2)}")
        if s["done"]:
            details = s["done"]["payload"]["details"]
            print(f"\nintents_selected: {details['intents_selected']}")
            live = details["retriever"].get("live_facts") or []
            print(f"live_facts: {len(live)}")
            if live:
                lf = live[0]
                print(f"  live table:   {lf['table']}")
                print(f"  live engine:  {lf['engine']}")
                print(f"  live rows:    {lf['row_count']}")
                print(f"  first 3 rows:")
                for r in lf["rows"][:3]:
                    print(f"    {r}")

            print(f"\nRESPONDER (bubble text):\n  {s['done']['text'].replace(chr(10), chr(10)+'  ')}")

        # Assertions
        assert s["retriever"], "no retriever_done frame"
        assert s["done"], "no agent_done frame"
        details = s["done"]["payload"]["details"]
        live = details["retriever"].get("live_facts") or []
        assert live, "live query didn't run — check the planner"
        assert live[0]["table"] == "orders"
        assert live[0]["row_count"] >= 1
        assert "Live: orders" in details["retriever"]["sources"]
        # Responder text must mention at least one real customer from the live rows
        customers_in_live = {row[0] if isinstance(row, list) else None for row in live[0]["rows"]}
        text_lower = s["done"]["text"].lower()
        assert any(c and c.lower() in text_lower for c in customers_in_live), \
            f"responder didn't cite a live-queried customer: {s['done']['text'][:300]!r}"

        print("\n===============================")
        print("LIVE-QUERY E2E PASSED ✓")
        print("===============================")
    finally:
        os.unlink(db_path)


if __name__ == "__main__":
    try:
        main()
    except AssertionError as e:
        print(f"\nFAIL: {e}", file=sys.stderr)
        sys.exit(1)
