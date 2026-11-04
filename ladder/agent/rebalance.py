"""prompt an llm for a rebalance and turn its answer into an assignment, or a named failure."""
import json
import os
import re
import time

from ladder.validate import explain

SYSTEM = ("you are the industrial engineer responsible for a paced assembly line. you answer with "
          "a station assignment as json and nothing else.")


def describe(s):
    """the prompt: the line as it is today plus the change in prose. the model has to apply the change."""
    n = s["n"]
    rows = "\n".join(f"  task {i + 1}: {s['base_times'][i]} s, after {s['base_preds'][i] if s['base_preds'][i] else 'nothing'}"
                     for i in range(n))
    m = s["base_stations"]
    stations = "\n".join(
        f"  station {k + 1}: tasks {[i + 1 for i in range(n) if s['base_assignment'][i] == k]}"
        f" ({sum(s['base_times'][i] for i in range(n) if s['base_assignment'][i] == k)} s)"
        for k in range(m))
    return f"""the line builds one product on {m} stations at a cycle time of {s['base_cycle_time']} s.
a task's listed predecessors must sit in the same station or an earlier one.

tasks (id: time, predecessors):
{rows}

current balance:
{stations}

change: {s['change']}

rebalance the line for the changed situation. use as few stations as you can. every task exactly once,
stations in line order, each station's total time within the cycle time, predecessors never downstream.
answer with json only, in this shape: {{"cycle_time": <int>, "stations": [[task ids], [task ids], ...]}}"""


def parse(text, n):
    """returns (assignment, failure) where exactly one is None."""
    body = text.strip()
    fence = re.search(r"```(?:json)?\s*(.*?)```", body, re.S)
    if fence:
        body = fence.group(1)
    start = body.find("{")
    end = body.rfind("}")
    if start < 0 or end < 0:
        return None, "no_json"
    try:
        obj = json.loads(body[start:end + 1])
    except json.JSONDecodeError:
        return None, "bad_json"
    stations = obj.get("stations") if isinstance(obj, dict) else None
    if not isinstance(stations, list) or not all(isinstance(st, list) for st in stations):
        return None, "bad_shape"
    assignment = [-1] * n
    seen = set()
    for k, st in enumerate(stations):
        for t in st:
            if not isinstance(t, int) or not (1 <= t <= n):
                return None, "unknown_task"
            if t in seen:
                return None, "duplicate_task"
            seen.add(t)
            assignment[t - 1] = k
    if len(seen) != n:
        return None, "missing_tasks"
    if any(len(st) == 0 for st in stations):
        return None, "empty_station"
    return assignment, None


def classify(inst, assignment, cycle_time):
    """first validator problem, as a failure mode label."""
    problems = explain(inst, assignment, cycle_time)
    if not problems:
        return None, []
    if any("exceeds cycle time" in p for p in problems) and not any("predecessor" in p for p in problems):
        return "cycle_time_exceeded", problems
    if any("predecessor" in p for p in problems) and not any("exceeds cycle time" in p for p in problems):
        return "precedence_violation", problems
    return "precedence_and_cycle_time", problems


def ask(model, prompt, temperature=0.0, max_tokens=16000, retries=4, thinking=None):
    """one chat call. retries only on transport or rate limit errors, never on a bad answer."""
    import cohere
    client = cohere.ClientV2(api_key=os.environ["COHERE_API_KEY"])
    for attempt in range(retries):
        try:
            t0 = time.perf_counter()
            kw = {}
            if thinking == "off":
                kw["thinking"] = {"type": "disabled"}
            elif thinking:
                kw["thinking"] = {"type": "enabled", "token_budget": int(thinking)}
            r = client.chat(model=model, temperature=temperature, max_tokens=max_tokens, **kw,
                            messages=[{"role": "system", "content": SYSTEM},
                                      {"role": "user", "content": prompt}])
            text = "".join(c.text for c in r.message.content if c.type == "text" and getattr(c, "text", None))
            thinking = sum(len(c.thinking or "") for c in r.message.content if c.type == "thinking")
            usage = r.usage.tokens if r.usage and r.usage.tokens else None
            meta = {"finish_reason": str(r.finish_reason), "thinking_chars": thinking,
                    "input_tokens": usage.input_tokens if usage else None,
                    "output_tokens": usage.output_tokens if usage else None}
            return text, time.perf_counter() - t0, meta
        except Exception as e:  # noqa: BLE001
            if attempt == retries - 1:
                raise
            time.sleep(5 * (attempt + 1))
