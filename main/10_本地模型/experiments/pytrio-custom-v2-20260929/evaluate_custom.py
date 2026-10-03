#!/usr/bin/env python3
"""Evaluate PyTRIO on the Laya v2 custom split; save only IDs and scores."""
from __future__ import annotations

import argparse
import asyncio
import json
import math
import os
import sys
import time
from pathlib import Path

from dotenv import load_dotenv


HERE = Path(__file__).resolve().parent
ROOT = next((p for p in HERE.parents if (p / "laya" / ".env").is_file()), None)
if ROOT is None:
    raise SystemExit("Cannot locate the workspace laya/.env")
ENV_PATH = ROOT / "laya" / ".env"
load_dotenv(ENV_PATH, override=False)
if not os.environ.get("PYTRIO_API_KEY") and os.environ.get("pytrio"):
    os.environ["PYTRIO_API_KEY"] = os.environ["pytrio"]
if not os.environ.get("PYTRIO_API_KEY"):
    raise SystemExit("No PyTRIO key found in laya/.env")

UPSTREAM = ROOT / "laya" / "experiments" / "pytrio-jev-20260928" / "upstream" / "09-pytrio-jev"
sys.path.insert(0, str(UPSTREAM))

import numpy as np
import pytrio as trio
from data import Encoder, load_jsonl, normalize_label, question_options
from inference import decide_async


def softmax_temperature(probabilities: list[float], temperature: float) -> list[float]:
    logits = [math.log(max(float(p), 1e-12)) / temperature for p in probabilities]
    peak = max(logits)
    exp = [math.exp(x - peak) for x in logits]
    total = sum(exp)
    return [x / total for x in exp]


def ece10(rows: list[dict]) -> float:
    if not rows:
        return float("nan")
    value = 0.0
    for bin_index in range(10):
        lo, hi = bin_index / 10, (bin_index + 1) / 10
        bucket = [r for r in rows if r["confidence"] >= lo and
                  (r["confidence"] < hi or (bin_index == 9 and r["confidence"] <= 1.0))]
        if bucket:
            accuracy = sum(r["correct"] for r in bucket) / len(bucket)
            confidence = sum(r["confidence"] for r in bucket) / len(bucket)
            value += len(bucket) / len(rows) * abs(accuracy - confidence)
    return value


def summarize(rows: list[dict]) -> dict:
    if not rows:
        return {"decisions": 0}
    return {
        "decisions": len(rows),
        "soft_cross_entropy": sum(r["soft_ce"] for r in rows) / len(rows),
        "argmax_accuracy": sum(r["correct"] for r in rows) / len(rows),
        "soft_brier": sum(r["soft_brier"] for r in rows) / len(rows),
        "ece10_hard_majority": ece10(rows),
    }


def attach_probabilities(records: list[dict], decisions: list[dict], temperature: float = 1.0) -> list[dict]:
    rows = []
    for record, result in zip(records, decisions):
        for field, question in record["questions"].items():
            option_values = [value for value, _ in question_options(question)]
            raw_map = result[field]["probabilities"]
            probs = [float(raw_map[value]) for value in option_values]
            if temperature != 1.0:
                probs = softmax_temperature(probs, temperature)
            target = normalize_label(question, record["targets"][field]["label"])
            predicted = option_values[int(np.argmax(probs))]
            soft_target = [float(v) for v in record["reference_soft_targets"][field]]
            if len(soft_target) != len(probs):
                raise ValueError(f"{record['id']}:{field}: probability and soft-label dimensions differ")
            rows.append({
                "id": record["id"],
                "field": field,
                "qtype": question["type"],
                "gold": str(target),
                "prediction": str(predicted),
                "correct": predicted == target,
                "confidence": max(probs),
                "soft_ce": -sum(q * math.log(max(p, 1e-12)) for q, p in zip(soft_target, probs)),
                "soft_brier": sum((p - q) ** 2 for q, p in zip(soft_target, probs)),
                "probabilities": {value: p for value, p in zip(option_values, probs)},
            })
    return rows


def fit_temperature(rows: list[dict]) -> float:
    """Golden-section minimization of vote-frequency soft CE on calibration only."""
    raw = []
    for row in rows:
        # Retain raw candidate distributions and target vectors in private fields
        # until the scalar calibration parameter has been selected.
        probs = list(row["_probs"])
        soft = list(row["_soft"])
        raw.append((probs, soft))

    def objective(temp: float) -> float:
        losses = []
        for probs, soft in raw:
            adjusted = softmax_temperature(probs, temp)
            losses.append(-sum(q * math.log(max(p, 1e-12)) for q, p in zip(soft, adjusted)))
        return sum(losses) / max(1, len(losses))

    left, right = 0.25, 4.0
    ratio = (math.sqrt(5.0) - 1.0) / 2.0
    x1 = right - ratio * (right - left)
    x2 = left + ratio * (right - left)
    f1, f2 = objective(x1), objective(x2)
    for _ in range(80):
        if f1 <= f2:
            right, x2, f2 = x2, x1, f1
            x1 = right - ratio * (right - left)
            f1 = objective(x1)
        else:
            left, x1, f1 = x1, x2, f2
            x2 = left + ratio * (right - left)
            f2 = objective(x2)
    return (left + right) / 2.0


async def query_records(client, encoder, records: list[dict], concurrency: int) -> list[dict]:
    semaphore = asyncio.Semaphore(concurrency)
    results: list[dict | None] = [None] * len(records)
    completed = 0

    async def one(index: int, record: dict) -> None:
        nonlocal completed
        async with semaphore:
            result = await decide_async(client, encoder, record, temperature=1.0)
        results[index] = result
        completed += 1
        if completed % 25 == 0 or completed == len(records):
            print(f"  sampled {completed}/{len(records)}", flush=True)

    await asyncio.gather(*(one(i, row) for i, row in enumerate(records)))
    return [r for r in results if r is not None]


async def evaluate(args: argparse.Namespace) -> dict:
    test_records = load_jsonl(args.test)
    calibration_records = load_jsonl(args.calibration) if args.calibration else []
    service = trio.ServiceClient()
    client = await service.create_sampling_client_async(base_model=args.base_model, model_path=args.weights)
    encoder = Encoder(client.get_tokenizer())

    print(f"Model: {args.base_model} | weights: {args.weights or 'base'}", flush=True)
    calibration_decisions = await query_records(client, encoder, calibration_records, args.concurrency) if calibration_records else []
    test_decisions = await query_records(client, encoder, test_records, args.concurrency)

    test_raw_rows = attach_probabilities(test_records, test_decisions, 1.0)
    raw_test = summarize(test_raw_rows)
    temperature = None
    calibration_raw_metrics = None
    calibration_scaled_metrics = None
    calibrated_test = None
    if calibration_records:
        calibration_rows = attach_probabilities(calibration_records, calibration_decisions, 1.0)
        calibration_raw_metrics = summarize(calibration_rows)
        temp_rows = []
        for record, result in zip(calibration_records, calibration_decisions):
            for field, question in record["questions"].items():
                values = [value for value, _ in question_options(question)]
                probs = [float(result[field]["probabilities"][value]) for value in values]
                temp_rows.append({
                    "_probs": probs,
                    "_soft": [float(x) for x in record["reference_soft_targets"][field]],
                })
        temperature = fit_temperature(temp_rows)
        calibration_scaled_metrics = summarize(attach_probabilities(calibration_records, calibration_decisions, temperature))
        calibrated_test = summarize(attach_probabilities(test_records, test_decisions, temperature))

    by_field = {}
    for field in sorted({r["field"] for r in test_raw_rows}):
        by_field[field] = summarize([r for r in test_raw_rows if r["field"] == field])
    result = {
        "model": args.base_model,
        "weights": args.weights,
        "test_records": len(test_records),
        "test_metrics_raw": raw_test,
        "test_metrics_temperature_scaled": calibrated_test,
        "calibration_records": len(calibration_records),
        "calibration_metrics_raw": calibration_raw_metrics,
        "calibration_metrics_temperature_scaled": calibration_scaled_metrics,
        "temperature": temperature,
        "test_metrics_by_field_raw": by_field,
        "test_predictions": test_raw_rows,
        "provenance": "DeepSeek 3-vote pseudo-labels; human review pending. Existing Laya test metrics have already been inspected.",
    }
    args.output_dir.mkdir(parents=True, exist_ok=True)
    path = args.output_dir / f"{args.tag}.json"
    path.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Wrote {path}", flush=True)
    print(json.dumps({"raw_test": raw_test, "temperature": temperature,
                      "calibrated_test": calibrated_test, "by_field": by_field}, ensure_ascii=False, indent=2))
    return result


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--test", type=Path, required=True)
    parser.add_argument("--calibration", type=Path, default=None)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--tag", required=True)
    parser.add_argument("--base-model", default="Qwen/Qwen3.5-4B")
    parser.add_argument("--weights", default=None)
    parser.add_argument("--concurrency", type=int, default=8)
    args = parser.parse_args()
    started = time.time()
    asyncio.run(evaluate(args))
    print(f"Elapsed seconds: {time.time() - started:.1f}")


if __name__ == "__main__":
    main()
