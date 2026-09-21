#!/usr/bin/env python3
"""Build, call, and evaluate a Jev citation-review request."""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any


DEFAULT_ENDPOINT = "https://api.typesafe.ai/v1/systemone"


def load_json(path: str) -> dict[str, Any]:
    value = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return value


def safe_id(value: str, index: int) -> str:
    slug = re.sub(r"[^A-Za-z0-9_]+", "_", value).strip("_").lower()
    return slug or f"item_{index}"


def validate_input(data: dict[str, Any]) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    items = data.get("items")
    if not isinstance(items, list) or not items:
        raise ValueError("input must contain a non-empty items array")

    normalized: list[dict[str, Any]] = []
    seen: set[str] = set()
    for index, item in enumerate(items, start=1):
        if not isinstance(item, dict):
            raise ValueError(f"items[{index - 1}] must be an object")
        claim = str(item.get("claim", "")).strip()
        evidence = str(item.get("evidence", "")).strip()
        if not claim or not evidence:
            raise ValueError(f"items[{index - 1}] requires non-empty claim and evidence")
        item_id = safe_id(str(item.get("id", f"item_{index}")), index)
        if item_id in seen:
            raise ValueError(f"duplicate normalized id: {item_id}")
        seen.add(item_id)
        normalized.append(
            {
                "id": item_id,
                "claim": claim,
                "evidence": evidence,
                "source_type": str(item.get("source_type", "")).strip(),
                "source_title": str(item.get("source_title", "")).strip(),
                "source_date": str(item.get("source_date", "")).strip(),
                "source_url": str(item.get("source_url", "")).strip(),
            }
        )

    raw_thresholds = data.get("thresholds") or {}
    if not isinstance(raw_thresholds, dict):
        raise ValueError("thresholds must be an object")
    thresholds = {
        "support": float(raw_thresholds.get("support", 0.70)),
        "risk": float(raw_thresholds.get("risk", 0.60)),
        "min_disposition_confidence": float(raw_thresholds.get("min_disposition_confidence", 0.50)),
        "reject_probability": float(raw_thresholds.get("reject_probability", 0.80)),
        "require_formal_source": bool(raw_thresholds.get("require_formal_source", True)),
    }
    for name in ("support", "risk", "min_disposition_confidence", "reject_probability"):
        if not 0 <= thresholds[name] <= 1:
            raise ValueError(f"{name} threshold must be between 0 and 1")
    return normalized, thresholds


def build_payload(items: list[dict[str, Any]], model: str) -> dict[str, Any]:
    questions: dict[str, Any] = {}
    for item in items:
        prefix = item["id"]
        questions[f"{prefix}_support"] = {
            "type": "choice",
            "instructions": f"For item {prefix}, does the supplied evidence support the full claim?",
            "criteria": {
                "supports": "The excerpt directly supports every material part of the claim",
                "insufficient": "The excerpt misses a material part or provides no usable support",
                "contradicts": "The excerpt conflicts with the claim",
            },
        }
        questions[f"{prefix}_disposition"] = {
            "type": "choice",
            "instructions": f"For item {prefix}, choose the publication disposition using only the supplied state.",
            "criteria": {
                "formal_source": "Suitable as the formal citation for this claim",
                "side_evidence": "Useful only as supporting context",
                "cannot_use": "Do not cite for this claim",
                "manual_review": "A person must inspect the original before deciding, including when source authority is unclear",
            },
        }
        questions[f"{prefix}_risk"] = {
            "type": "noul",
            "instructions": f"For item {prefix}, does the supplied claim and excerpt show an obvious semantic conflict or overclaim risk likely to mislead a reader?",
        }
    return {"state": items, "model": model, "questions": questions}


def call_jev(payload: dict[str, Any], endpoint: str, api_key: str, timeout: int) -> dict[str, Any]:
    request = urllib.request.Request(
        endpoint,
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            result = json.loads(response.read().decode("utf-8"))
            if not isinstance(result, dict):
                raise RuntimeError("Jev returned a non-object JSON response")
            result.setdefault("http_status", response.status)
            return result
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"Jev HTTP {exc.code}: {detail}") from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(f"Jev request failed: {exc.reason}") from exc


def answer(response: dict[str, Any], key: str) -> dict[str, Any]:
    answers = response.get("answers")
    if not isinstance(answers, dict) or not isinstance(answers.get(key), dict):
        raise ValueError(f"response is missing answer: {key}")
    return answers[key]


def evaluate(items: list[dict[str, Any]], thresholds: dict[str, Any], response: dict[str, Any]) -> list[dict[str, Any]]:
    decisions: list[dict[str, Any]] = []
    for item in items:
        prefix = item["id"]
        support = answer(response, f"{prefix}_support")
        disposition = answer(response, f"{prefix}_disposition")
        risk_answer = answer(response, f"{prefix}_risk")

        support_probs = support.get("probabilities") or {}
        disposition_probs = disposition.get("probabilities") or {}
        support_p = float(support_probs.get("supports", 0.0))
        risk_p = float(risk_answer.get("noul", 0.0))
        support_choice = support.get("choice")
        disposition_choice = disposition.get("choice")
        disposition_confidence = disposition.get("confidence")
        disposition_confidence_value = float(disposition_confidence) if disposition_confidence is not None else 0.0

        reasons: list[str] = []
        if support_p < thresholds["support"]:
            reasons.append(f"support {support_p:.2f} < {thresholds['support']:.2f}")
        if risk_p > thresholds["risk"]:
            reasons.append(f"risk {risk_p:.2f} > {thresholds['risk']:.2f}")
        if thresholds["require_formal_source"] and disposition_choice != "formal_source":
            reasons.append(f"disposition is {disposition_choice}")
        if disposition_confidence_value < thresholds["min_disposition_confidence"]:
            reasons.append(
                f"disposition confidence {disposition_confidence_value:.2f} < "
                f"{thresholds['min_disposition_confidence']:.2f}"
            )

        contradiction_p = float(support_probs.get("contradicts", 0.0))
        cannot_use_p = float(disposition_probs.get("cannot_use", 0.0))
        if max(contradiction_p, cannot_use_p) >= thresholds["reject_probability"]:
            status = "reject"
        elif reasons:
            status = "manual_review"
        else:
            status = "pass"

        decisions.append(
            {
                "id": prefix,
                "claim": item["claim"],
                "source_url": item.get("source_url", ""),
                "support_choice": support_choice,
                "support_probability": support_p,
                "support_confidence": support.get("confidence"),
                "disposition": disposition_choice,
                "disposition_probability": disposition_probs.get(disposition_choice),
                "disposition_confidence": disposition_confidence,
                "risk_probability": risk_p,
                "status": status,
                "reasons": reasons,
            }
        )
    return decisions


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", help="JSON file containing items and optional thresholds")
    parser.add_argument("--output", help="Write JSON result to this path; stdout when omitted")
    parser.add_argument("--endpoint", default=DEFAULT_ENDPOINT)
    parser.add_argument("--model", default="jev-latest")
    parser.add_argument("--api-key-env", default="TYPESAFE_API_KEY")
    parser.add_argument("--timeout", type=int, default=60)
    parser.add_argument("--dry-run", action="store_true", help="Print the API request without sending it")
    parser.add_argument("--response-file", help="Evaluate this saved Jev response instead of calling the API")
    args = parser.parse_args()

    try:
        data = load_json(args.input)
        items, thresholds = validate_input(data)
        payload = build_payload(items, args.model)

        if args.dry_run:
            result: dict[str, Any] = {"request": payload, "thresholds": thresholds}
        else:
            if args.response_file:
                response = load_json(args.response_file)
            else:
                api_key = os.environ.get(args.api_key_env) or os.environ.get("JEV_API_KEY")
                if not api_key:
                    raise ValueError(
                        f"missing API key: set {args.api_key_env} or JEV_API_KEY, "
                        "or use --response-file"
                    )
                response = call_jev(payload, args.endpoint, api_key, args.timeout)
            result = {
                "model": response.get("model"),
                "thresholds": thresholds,
                "decisions": evaluate(items, thresholds, response),
                "raw_response": response,
            }

        rendered = json.dumps(result, ensure_ascii=False, indent=2) + "\n"
        if args.output:
            Path(args.output).write_text(rendered, encoding="utf-8")
        else:
            sys.stdout.write(rendered)
        return 0
    except (OSError, ValueError, RuntimeError, json.JSONDecodeError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
