#!/usr/bin/env bash
# reproduce everything: data, tests, benchmark, simulation sweep, comsoal sweep, agent runs, charts.
# usage: bash run.sh <label>   (results land in results/<label>/)
# exits non-zero the moment any solution fails validation (the validator raises, nothing catches it).
set -euo pipefail
label="${1:?usage: bash run.sh <label>}"
cd "$(dirname "$0")"
python tools/fetch_data.py
python -m pytest -q tests
python bench/run_benchmark.py --label "$label" --time-limit 20 --sample 40
python bench/comsoal_sweep.py --label "$label"
python bench/run_sim.py --label "$label"
if [ -n "${COHERE_API_KEY:-}" ]; then
  python bench/run_agent.py --label "$label" --model command-a-plus-05-2026 --max-tokens 32000
  python bench/run_agent.py --label "$label" --model command-a-03-2025 --max-tokens 8192
else
  echo "COHERE_API_KEY not set, skipping the agent runs"
fi
python bench/charts.py --label "$label"
echo "done: results/$label"
