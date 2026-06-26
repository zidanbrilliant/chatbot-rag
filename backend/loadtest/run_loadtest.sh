#!/bin/bash
# Load test runner for chatbot backend.
# Usage: ./run_loadtest.sh [base_url] [duration_sec] [threads] [connections]
#
# Requires: wrk (apt install wrk OR brew install wrk)
# Requires: JWT_TOKEN env var (valid system_admin token)

set -e

BASE_URL="${1:-http://localhost:8000}"
DURATION="${2:-60}"
THREADS="${3:-4}"
CONNECTIONS="${4:-100}"

if [ -z "$JWT_TOKEN" ]; then
  echo "ERROR: JWT_TOKEN env var not set"
  echo "Get one with:"
  echo "  curl -X POST $BASE_URL/api/v1/auth/login -H 'Content-Type: application/json' \\"
  echo "    -d '{\"username\":\"admin\",\"password\":\"<ADMIN_PASSWORD>\"}' | jq -r .token"
  exit 1
fi

QUERY_PAYLOAD='{"query":"apa itu SOP cuti tahunan?","session_id":null}'
CASUAL_PAYLOAD='{"query":"halo","session_id":null}'

mkdir -p /tmp/loadtest

# Build Lua script for mixed workload
cat > /tmp/loadtest/mixed.lua <<'EOF'
wrk.method = "POST"
wrk.headers["Content-Type"] = "application/json"
wrk.headers["Authorization"] = "Bearer " .. os.getenv("JWT_TOKEN")

local query_payload = os.getenv("QUERY_PAYLOAD")
local casual_payload = os.getenv("CASUAL_PAYLOAD")

request = function()
  -- 70% RAG query, 30% casual greeting
  if math.random() < 0.7 then
    wrk.body = query_payload
  else
    wrk.body = casual_payload
  end
  return wrk.format(nil, nil, wrk.body)
end
EOF

export JWT_TOKEN QUERY_PAYLOAD CASUAL_PAYLOAD

echo "=== Load test: $BASE_URL ==="
echo "Duration: ${DURATION}s | Threads: $THREADS | Connections: $CONNECTIONS"
echo

# Warmup run (discarded)
echo "Warmup (5s)..."
wrk -t2 -c10 -d5s -s /tmp/loadtest/mixed.lua "$BASE_URL/api/v1/chat/query" > /dev/null 2>&1 || true

# Actual test
echo "Main run..."
wrk -t"$THREADS" -c"$CONNECTIONS" -d"${DURATION}s" \
  --latency -s /tmp/loadtest/mixed.lua \
  "$BASE_URL/api/v1/chat/query"

echo
echo "Done. Check /tmp/loadtest/ for HTML reports."
