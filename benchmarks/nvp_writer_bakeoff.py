#!/usr/bin/env python3
"""NVP-WRITE-01: offline, model-neutral screenplay-writing comparison.

Run against a separately loaded local OpenAI-compatible chat completion server.
Never sends private scripts to remote endpoints. Records raw output for blind review;
it does not claim to score acting or writing quality automatically.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import re
import time
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import HTTPRedirectHandler, ProxyHandler, Request, build_opener


CASES = [
    {
        "id": "novice_idea",
        "category": "creative",
        "prompt": (
            "A bus driver discovers a passenger who never appears on security cameras. "
            "A lonely woman might be in danger. Write three distinctly different filmable "
            "loglines, and for each explain its emotional conflict in one sentence. "
            "Avoid generic movie marketing language."
        ),
    },
    {
        "id": "dialogue_subtext",
        "category": "creative",
        "prompt": (
            "Write 1–2 pages of Fountain-formatted screenplay for this scene: "
            "INT. DINER - NIGHT. MARA wants her brother ELI to confess that he sold their "
            "mother's ring. ELI knows it was stolen before he arrived, but promised "
            "not to reveal who took it. MARA also knows the ring was stolen, but hopes "
            "his explanation will reveal a different secret. Both care about each other. "
            "Use spare physical action, distinct voices, and meaningful silence. "
            "No explanatory narration about inner thoughts. End with a choice."
        ),
    },
    {
        "id": "protected_edit",
        "category": "hard_constraint",
        "prompt": (
            "Change ONLY the line 'I suppose you stayed late.' into a subtler expression "
            "of suspicion. Preserve all other text exactly, including scene heading, "
            "spacing, action and other dialogue. Return the entire excerpt only.\n\n"
            "INT. HALLWAY - NIGHT\n\nMARA holds a wet umbrella.\n\nMARA\n"
            "I suppose you stayed late.\n\nJON\nThe bus never came.\n\n"
            "MARA closes the umbrella.\n\nJON\nDid the lights go out here, too?"
        ),
    },
    {
        "id": "nonlinear_continuity",
        "category": "continuity",
        "prompt": (
            "Audit these scenes, which are presented out of chronological order. "
            "Return a JSON object with keys confirmed, contradictions, and unknowns. "
            "Do not turn claims into facts.\n\n"
            "Scene 8, Tuesday night: RAVI says that he knows the vault code, "
            "but the audience has not seen him learn it.\n"
            "Scene 3, Monday evening: LENA locks the silver key in a blue box. "
            "She alone knows the vault code.\n"
            "Scene 5, Tuesday morning: RAVI opens the blue box and removes the "
            "silver key. The script does not show how he opened the box.\n"
            "Scene 2, Monday afternoon: RAVI tries and fails to open the vault."
        ),
    },
    {
        "id": "scene_to_structure",
        "category": "production",
        "prompt": (
            "Convert the scene into valid JSON only: location, speakers with stable names, "
            "dialogue (speaker and text), props and ownership changes. Do not invent actions.\n\n"
            "INT. KITCHEN - MORNING\n\nARLO places the red notebook on the table.\n\n"
            "ARLO\nDon't open it yet.\n\nMIRA\nI wasn't going to.\n\n"
            "Mira picks up the notebook."
        ),
    },
]


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, request, fp, code, msg, headers, newurl):
        return None


def validate_endpoint(url: str) -> str:
    p = urlparse(url)
    if (p.scheme != "http" or p.hostname not in {"127.0.0.1", "localhost", "::1"}
            or p.port is None or p.path != "/v1/chat/completions"
            or p.username is not None or p.password is not None
            or p.query or p.fragment):
        raise ValueError("Only local HTTP /v1/chat/completions endpoints are supported")
    return url


def run_case(endpoint: str, model: str, case: dict, *, temperature: float,
             top_p: float, max_tokens: int, timeout: int) -> dict:
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": (
                "You are a collaborative screenplay writer and continuity assistant. "
                "The creator controls the story. Respect precise editing constraints, "
                "established facts and requested screenplay format. Reply with the work only.")},
            {"role": "user", "content": case["prompt"]},
        ],
        "temperature": temperature,
        "top_p": top_p,
        "max_tokens": max_tokens,
        "stream": False,
    }
    request = Request(endpoint, json.dumps(payload).encode("utf-8"),
                      {"Content-Type": "application/json"}, method="POST")
    start = time.perf_counter()
    try:
        # Avoid environment proxies and refuse all redirects: scripts stay local.
        with build_opener(ProxyHandler({}), NoRedirect()).open(request, timeout=timeout) as response:
            content = response.read(2_000_001)
        if len(content) > 2_000_000:
            raise ValueError("Response exceeded 2 MB")
        parsed = json.loads(content)
        choice = parsed["choices"][0]
        output = choice["message"].get("content") or ""
        if not isinstance(output, str):
            raise ValueError("Invalid model output")
        result = {"output": output, "finish_reason": choice.get("finish_reason"),
                  "usage": parsed.get("usage"), "error": None}
    except (HTTPError, URLError, TimeoutError, ValueError, KeyError, IndexError,
            TypeError, json.JSONDecodeError) as exc:
        result = {"output": "", "finish_reason": None, "usage": None, "error": str(exc)}
    result.update({"id": case["id"], "category": case["category"],
                   "elapsed_seconds": round(time.perf_counter() - start, 2)})
    return result


def evaluate_hard_constraints(results: list[dict]) -> list[dict]:
    """Objective checks only. Does not pretend to rate creative quality."""
    findings = []
    excerpt = "INT. HALLWAY - NIGHT\n\nMARA holds a wet umbrella.\n\nMARA\nI suppose you stayed late.\n\nJON\nThe bus never came.\n\nMARA closes the umbrella.\n\nJON\nDid the lights go out here, too?"
    fixed = excerpt.split("I suppose you stayed late.")
    for item in results:
        if item["id"] == "protected_edit" and not item["error"]:
            output = item["output"]
            correct = (output.startswith(fixed[0]) and output.endswith(fixed[1])
                       and output.count(fixed[0]) == 1 and output.count(fixed[1]) == 1
                       and "I suppose you stayed late." not in output)
            findings.append({"id": item["id"], "passed": correct,
                             "check": "unchanged prefix and suffix around exactly one changed line"})
        elif item["id"] in {"nonlinear_continuity", "scene_to_structure"} and not item["error"]:
            try:
                parsed = json.loads(item["output"])
                valid = isinstance(parsed, dict)
            except json.JSONDecodeError:
                valid = False
            findings.append({"id": item["id"], "passed": valid,
                             "check": "parseable JSON object (not semantic correctness)"})
    return findings


def main(argv=None):
    parser = argparse.ArgumentParser(description="NVP local screenplay model comparison")
    parser.add_argument("--url", type=validate_endpoint, required=True)
    parser.add_argument("--model", required=True, help="Model ID of the locally loaded model")
    parser.add_argument("--alias", required=True, choices=["A", "B", "C"],
                        help="Blind comparison label. Keep model-to-label key separately")
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--repeat", type=int, default=2)
    parser.add_argument("--temperature", type=float, default=0.7)
    parser.add_argument("--top-p", type=float, default=0.9)
    parser.add_argument("--max-tokens", type=int, default=6000)
    parser.add_argument("--timeout", type=int, default=300)
    args = parser.parse_args(argv)
    if not (1 <= args.repeat <= 5 and 0 <= args.temperature <= 2
            and 0 < args.top_p <= 1 and 512 <= args.max_tokens <= 32768
            and 5 <= args.timeout <= 3600):
        parser.error("Sampling/time limits are out of bounds")
    if args.out.exists():
        parser.error("Output already exists; choose a new path to preserve test history")
    rows = []
    for run in range(1, args.repeat + 1):
        for case in CASES:
            row = run_case(args.url, args.model, case, temperature=args.temperature,
                           top_p=args.top_p, max_tokens=args.max_tokens,
                           timeout=args.timeout)
            row["run"] = run
            rows.append(row)
            print(f"{case['id']} / run {run}: " + ("ERROR" if row["error"] else "captured"))
    record = {"schema": "nvp_writer_bakeoff_v1", "alias": args.alias,
              "settings": {"temperature": args.temperature, "top_p": args.top_p,
                           "max_tokens": args.max_tokens, "repeat": args.repeat},
              "results": rows, "objective_checks": evaluate_hard_constraints(rows)}
    args.out.parent.mkdir(parents=True, exist_ok=True)
    # Exclusive create means accidental overwrite is not permitted.
    with args.out.open("x", encoding="utf-8") as f:
        json.dump(record, f, indent=2, ensure_ascii=False)
    print(f"Saved {len(rows)} captured responses to {args.out}. Human creative review still required.")


if __name__ == "__main__":
    main()
