"""One-off helper to drive the /api/jobs/corpus endpoints from inside the
backend container, where curl isn't installed (python:3.11-slim). Not part
of the app itself - just a convenience script for manual runs on the VPS.

Usage (inside the container, e.g. `docker compose exec backend python corpus_cli_test.py`):
  EMAIL=you@example.com PASSWORD=yourpassword python corpus_cli_test.py [target_words]
"""
import os
import sys
import time

import requests

BASE = "http://localhost:8000"
email = os.environ["EMAIL"]
password = os.environ["PASSWORD"]
target_words = int(sys.argv[1]) if len(sys.argv) > 1 else 700_000

login = requests.post(f"{BASE}/api/auth/login", json={"email": email, "password": password})
login.raise_for_status()
token = login.json()["access_token"]
headers = {"Authorization": f"Bearer {token}"}

start = requests.post(f"{BASE}/api/jobs/corpus/start", json={"target_words": target_words}, headers=headers)
start.raise_for_status()
run = start.json()
run_id = run["id"]
print(f"Started run {run_id}, target {target_words} words.")

while True:
    status = requests.get(f"{BASE}/api/jobs/corpus/{run_id}", headers=headers).json()
    print(f"  {status['status']}: {status['collected_words']}/{target_words} words, "
          f"{status['posting_count']} postings - {status.get('current_step')}")
    if status["status"] in ("done", "failed"):
        break
    time.sleep(10)

if status["status"] == "failed":
    print(f"FAILED: {status.get('error')}")
    sys.exit(1)

out = requests.get(f"{BASE}/api/jobs/corpus/{run_id}/download", headers=headers)
out.raise_for_status()
with open("/data/corpus/jobs_downloaded.jsonl", "wb") as f:
    f.write(out.content)
print("Saved to /data/corpus/jobs_downloaded.jsonl (inside the container - copy out with "
      "`docker compose cp backend:/data/corpus/jobs_downloaded.jsonl .` from the host).")
