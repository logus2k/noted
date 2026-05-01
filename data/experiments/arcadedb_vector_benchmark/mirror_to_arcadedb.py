"""Mirror gr_entities dump into ArcadeDB sandbox DB `vector_bench`.

Drops the type if present, re-creates schema + LSM_VECTOR index, then
batch-inserts all entries with their precomputed bge-m3 embeddings.
"""

import json
import time
import urllib.request
import urllib.error
from base64 import b64encode

ARCADE = "http://localhost:2480"
DB = "vector_bench"
USER = "root"
PWD = "noted-dev"
DUMP = "/home/logus/env/assets/noted/data/experiments/arcadedb_vector_benchmark/gr_entities_dump.json"

AUTH = "Basic " + b64encode(f"{USER}:{PWD}".encode()).decode()


def cmd(language: str, command: str, db: str = DB):
    body = json.dumps({"language": language, "command": command}).encode()
    req = urllib.request.Request(
        f"{ARCADE}/api/v1/command/{db}",
        data=body,
        headers={"Authorization": AUTH, "Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=120) as r:
            return json.loads(r.read())
    except urllib.error.HTTPError as e:
        return {"error": e.read().decode(errors="replace")}


def cmd_with_params(language: str, command: str, params: dict, db: str = DB):
    body = json.dumps({"language": language, "command": command, "params": params}).encode()
    req = urllib.request.Request(
        f"{ARCADE}/api/v1/command/{db}",
        data=body,
        headers={"Authorization": AUTH, "Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=120) as r:
            return json.loads(r.read())
    except urllib.error.HTTPError as e:
        return {"error": e.read().decode(errors="replace")}


def reset_schema():
    print("=== reset schema ===")
    # Drop the type if present (cascades to index)
    r = cmd("sql", "DROP TYPE GrEntity IF EXISTS UNSAFE")
    print("drop:", r.get("result", r))
    r = cmd("sql", "CREATE VERTEX TYPE GrEntity")
    print("type:", r.get("result", r))
    r = cmd("sql", "CREATE PROPERTY GrEntity.id STRING")
    print("prop id:", r.get("result", r))
    r = cmd("sql", "CREATE PROPERTY GrEntity.text STRING")
    print("prop text:", r.get("result", r))
    r = cmd("sql", "CREATE PROPERTY GrEntity.embedding ARRAY_OF_FLOATS")
    print("prop emb:", r.get("result", r))
    r = cmd("sql", "CREATE INDEX ON GrEntity (id) UNIQUE")
    print("idx id:", r.get("result", r))
    r = cmd(
        "sql",
        "CREATE INDEX ON GrEntity (embedding) LSM_VECTOR METADATA "
        "{ dimensions: 1024, similarity: 'COSINE' }",
    )
    print("idx vec:", r.get("result", r))


def insert_batch(rows):
    """Insert one entity per call (simplest, avoids any UNWIND quirks)."""
    for row in rows:
        r = cmd_with_params(
            "sql",
            "INSERT INTO GrEntity SET id = :id, text = :text, embedding = :emb",
            {"id": row["id"], "text": row["text"], "emb": row["embedding"]},
        )
        if "error" in r:
            print("ERR insert", row["id"], "::", r["error"][:200])
            return False
    return True


def main():
    reset_schema()

    print("=== load dump ===")
    with open(DUMP) as f:
        data = json.load(f)
    print(f"entries: {len(data)}, dim: {len(data[0]['embedding'])}")

    print("=== insert ===")
    t0 = time.time()
    BATCH = 50
    for i in range(0, len(data), BATCH):
        ok = insert_batch(data[i : i + BATCH])
        if not ok:
            print(f"halted at batch {i}")
            return
        if i % 200 == 0:
            elapsed = time.time() - t0
            print(f"  {i}/{len(data)} ({elapsed:.1f}s)")
    print(f"done in {time.time() - t0:.1f}s")

    print("=== verify count ===")
    r = cmd("sql", "SELECT count(*) AS n FROM GrEntity")
    print("count:", r.get("result"))


if __name__ == "__main__":
    main()
