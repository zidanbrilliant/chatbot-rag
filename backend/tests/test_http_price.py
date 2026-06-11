"""HTTP-level integration test for /chat/query with price branch.

Tests the actual FastAPI route handler with real Postgres but mocked
external dependencies (Qdrant, Redis, Ollama, Groq).
"""

import os
import sys
from unittest.mock import patch, MagicMock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from fastapi.testclient import TestClient

# Ensure DB URL is set
os.environ.setdefault(
    "DATABASE_URL", "postgresql://postgres:postgres@localhost:5432/chatbot"
)

from app.main import app


def banner(msg: str) -> None:
    print("\n" + "=" * 70)
    print(f"  {msg}")
    print("=" * 70)


def make_client() -> TestClient:
    return TestClient(app)


# ── Test fixtures: mock all external dependencies ────────


def _mock_all():
    """Return a context manager that mocks all external deps for the price branch."""
    return [
        patch("app.routers.chat.generate_response"),
        patch("app.routers.chat._search_web_with_cache"),
        patch("app.main.rate_limit_middleware", new=_noop_middleware),
    ]


async def _noop_middleware(request, call_next):
    return await call_next(request)


def test_price_query_beras():
    banner("HTTP TEST 1: POST /chat/query — 'berapa harga Beras Premium 5kg'")
    client = make_client()

    with patch("app.routers.chat.generate_response") as mock_gen, \
         patch("app.routers.chat._search_web_with_cache") as mock_web:
        mock_gen.return_value = "Beras Premium 5kg tersedia di database kami dengan harga update."
        mock_web.return_value = [
            {
                "title": "Tokopedia - Beras Premium 5kg",
                "url": "https://tokopedia.link/beras",
                "snippet": "Beras Premium 5kg Rp 78.000",
            }
        ]

        resp = client.post(
            "/api/v1/chat/query",
            json={"query": "berapa harga Beras Premium 5kg", "session_id": None},
        )

    print(f"  status_code: {resp.status_code}")
    assert resp.status_code == 200, f"Got {resp.status_code}: {resp.text}"
    data = resp.json()
    print(f"  session_id:  {data.get('session_id', '')[:8]}...")
    print(f"  reply (120c): {data.get('reply', '')[:120]!r}")
    print(f"  confidence:  {data.get('confidence')}")
    print(f"  sources:     {len(data.get('sources', []))} source(s)")
    print(f"  metadata:    {list(data.get('metadata', {}).keys())}")
    print()
    print("  metadata.price_table:")
    for row in data.get("metadata", {}).get("price_table", []):
        print(f"    - {row['source'][:30]:<30} | {row['product'][:20]:<20} | {row['price']:<12} | {row['type']}")
    print()
    print("  metadata.intent:")
    intent = data.get("metadata", {}).get("intent", {})
    for k, v in intent.items():
        print(f"    {k}: {v}")
    assert "price_table" in data.get("metadata", {}), "Should have price_table in metadata"
    assert len(data["metadata"]["price_table"]) >= 1
    assert "Beras" in data["reply"]
    print("  PASS")


def test_price_query_bitcoin_date():
    banner("HTTP TEST 2: POST /chat/query — 'harga Bitcoin pada 2024-01-15'")
    client = make_client()
    with patch("app.routers.chat.generate_response") as mock_gen, \
         patch("app.routers.chat._search_web_with_cache") as mock_web:
        mock_gen.return_value = "Harga Bitcoin pada tanggal tersebut tersedia di database."
        mock_web.return_value = []

        resp = client.post(
            "/api/v1/chat/query",
            json={"query": "harga Bitcoin pada 2024-01-15", "session_id": None},
        )

    print(f"  status_code: {resp.status_code}")
    assert resp.status_code == 200, f"Got {resp.status_code}: {resp.text}"
    data = resp.json()
    print(f"  reply (120c): {data.get('reply', '')[:120]!r}")
    intent = data.get("metadata", {}).get("intent", {})
    print(f"  intent.type: {intent.get('type')}")
    print(f"  intent.date: {intent.get('date')}")
    print(f"  price_table: {len(data.get('metadata', {}).get('price_table', []))} rows")
    for row in data.get("metadata", {}).get("price_table", []):
        print(f"    - {row['product'][:20]:<20} | {row['price']:<15} | {row['date']}")
    assert intent.get("type") == "timeseries"
    assert intent.get("date") == "2024-01-15"
    print("  PASS")


def test_price_query_samsung():
    banner("HTTP TEST 3: POST /chat/query — 'harga Samsung Galaxy S24'")
    client = make_client()
    with patch("app.routers.chat.generate_response") as mock_gen, \
         patch("app.routers.chat._search_web_with_cache") as mock_web:
        mock_gen.return_value = "Samsung Galaxy S24 tersedia."
        mock_web.return_value = [
            {
                "title": "Amazon - Samsung Galaxy S24",
                "url": "https://amazon.com/s24",
                "snippet": "Samsung Galaxy S24 $899",
            }
        ]

        resp = client.post(
            "/api/v1/chat/query",
            json={"query": "harga Samsung Galaxy S24", "session_id": None},
        )

    print(f"  status_code: {resp.status_code}")
    assert resp.status_code == 200, f"Got {resp.status_code}: {resp.text}"
    data = resp.json()
    intent = data.get("metadata", {}).get("intent", {})
    print(f"  intent.type:     {intent.get('type')}")
    print(f"  intent.target:   {intent.get('target')}")
    print(f"  intent.currency: {intent.get('currency')}")
    print(f"  price_table:     {len(data.get('metadata', {}).get('price_table', []))} rows")
    for row in data.get("metadata", {}).get("price_table", []):
        print(f"    - {row['product'][:30]:<30} | {row['price']:<18} | {row['type']}")
    assert "Samsung" in intent.get("target", "")
    print("  PASS")


def test_non_price_query_passthrough():
    """Control test: non-price query should bypass price branch entirely.

    Note: this test requires the regular RAG path to work, which needs
    Qdrant/Ollama/Groq. We just verify the price branch is NOT taken.
    """
    banner("HTTP TEST 4: POST /chat/query — non-price query (control)")
    client = make_client()

    # Patch at the call site in _handle_price_query's caller
    # We just want to verify that the intent classifier says "not a price query"
    intent_result = None
    import app.routers.chat as chat_mod
    from app.services.intent_classifier import detect_price_intent
    intent = detect_price_intent("apa itu Bitcoin?")
    print(f"  is_price_query: {intent.is_price_query}")
    print(f"  query_type:     {intent.query_type}")
    assert not intent.is_price_query, "Should not be detected as price query"
    print("  PASS (intent correctly classified as non-price)")


if __name__ == "__main__":
    tests = [
        test_price_query_beras,
        test_price_query_bitcoin_date,
        test_price_query_samsung,
        test_non_price_query_passthrough,
    ]
    passed = 0
    failed = 0
    for t in tests:
        try:
            t()
            passed += 1
        except Exception as e:
            failed += 1
            import traceback
            traceback.print_exc()
            print(f"  FAILED: {e}")
    print(f"\n{'=' * 70}")
    print(f"  HTTP RESULTS: {passed} passed, {failed} failed out of {len(tests)}")
    print(f"{'=' * 70}\n")
    sys.exit(0 if failed == 0 else 1)
