"""Backfill access_level='internal' on Qdrant points that lack it.

Ponytail: one-shot migration script. Run from backend/.
"""
import json
import os
import sys
import urllib.request

from app.config import QDRANT_COLLECTION, QDRANT_HOST, QDRANT_PORT


def main() -> int:
    base = f"http://{QDRANT_HOST}:{QDRANT_PORT}"
    points = []
    offset = None
    while True:
        body = {"limit": 200, "with_payload": True, "with_vector": False}
        if offset is not None:
            body["offset"] = offset
        req = urllib.request.Request(
            f"{base}/collections/{QDRANT_COLLECTION}/points/scroll",
            data=json.dumps(body).encode(),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        r = urllib.request.urlopen(req, timeout=10)
        result = json.loads(r.read())["result"]
        points.extend(result["points"])
        offset = result.get("next_page_offset")
        if offset is None:
            break

    missing = [p for p in points if "access_level" not in p.get("payload", {})]
    print(f"total: {len(points)}, missing access_level: {len(missing)}")
    if not missing:
        print("Nothing to backfill.")
        return 0

    req = urllib.request.Request(
        f"{base}/collections/{QDRANT_COLLECTION}/points/payload",
        data=json.dumps({"payload": {"access_level": "internal"}, "points": [p["id"] for p in missing]}).encode(),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    r = urllib.request.urlopen(req, timeout=30)
    print("backfill result:", json.loads(r.read()))

    return 0


if __name__ == "__main__":
    sys.exit(main())
