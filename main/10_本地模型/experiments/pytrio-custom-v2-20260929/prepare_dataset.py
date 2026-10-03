#!/usr/bin/env python3
"""Convert reviewed-schema Laya candidates to PyTRIO-Jev canonical records.

This is an exploratory pseudo-label experiment. It preserves the source-group
split and never trains on dev, calibration, or test records.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from collections import Counter, defaultdict
from pathlib import Path


EXPECTED = {"train": 1200, "dev": 200, "calibration": 100, "test": 400}


def read_jsonl(path: Path) -> list[dict]:
    rows = []
    with path.open(encoding="utf-8") as handle:
        for line_no, line in enumerate(handle, 1):
            if not line.strip():
                continue
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError as exc:
                raise ValueError(f"{path}:{line_no}: invalid JSON") from exc
    return rows


def write_jsonl(path: Path, rows: list[dict]) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False, separators=(",", ":")) + "\n")
    return hashlib.sha256(path.read_bytes()).hexdigest()


def convert(record: dict) -> dict:
    split = record.get("metadata", {}).get("planned_split")
    if split not in EXPECTED:
        raise ValueError(f"{record.get('id')}: invalid planned split {split!r}")
    if record.get("metadata", {}).get("review_status") != "needs_human_review":
        raise ValueError(f"{record.get('id')}: unexpected review state")
    if record.get("metadata", {}).get("label_rounds") != 3:
        raise ValueError(f"{record.get('id')}: expected exactly 3 label votes")
    if len(record.get("qs", [])) != 5:
        raise ValueError(f"{record.get('id')}: expected exactly 5 decision fields")

    questions: dict[str, dict] = {}
    targets: dict[str, dict[str, str]] = {}
    soft_targets: dict[str, list[float]] = {}
    for source_question in record["qs"]:
        field = source_question["id"]
        kind = source_question["t"]
        criteria = source_question["crit"]
        y = source_question["y"]
        soft = source_question["soft"]
        if len(soft) != (len(criteria) if not isinstance(criteria, dict) else len(criteria)):
            raise ValueError(f"{record['id']}:{field}: soft target size mismatch")
        if abs(sum(soft) - 1.0) > 1e-6:
            raise ValueError(f"{record['id']}:{field}: soft target must sum to 1")

        if kind == "choice":
            labels = list(criteria)
            if not 0 <= y < len(labels):
                raise ValueError(f"{record['id']}:{field}: choice index out of range")
            question = {"type": "choice", "instructions": source_question["ins"], "criteria": criteria}
            label = labels[y]
        elif kind == "noul":
            labels = list(criteria)
            if set(labels) != {"false", "true"} or not 0 <= y < 2:
                raise ValueError(f"{record['id']}:{field}: malformed boolean decision")
            # PyTRIO's constrained answer order is no, yes, matching the source's
            # false, true vector and keeping the soft-target dimensions aligned.
            question = {"type": "noul", "instructions": source_question["ins"], "criteria": criteria}
            label = "yes" if labels[y] == "true" else "no"
        elif kind == "score":
            if not 0 <= y < len(criteria):
                raise ValueError(f"{record['id']}:{field}: score index out of range")
            question = {"type": "score", "instructions": source_question["ins"], "criteria": criteria}
            label = str(y)
        else:
            raise ValueError(f"{record['id']}:{field}: unsupported question kind {kind!r}")

        questions[field] = question
        targets[field] = {"label": label}
        soft_targets[field] = [float(value) for value in soft]

    return {
        "id": record["id"],
        "state": record["state"],
        "questions": questions,
        "targets": targets,
        "reference_soft_targets": soft_targets,
        "source_group_id": record["source_group_id"],
        "planned_split": split,
        "label_provenance": "3-round DeepSeek pseudo-label vote; not human reviewed",
        "review_status": "needs_human_review",
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--candidates", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()

    candidates = read_jsonl(args.candidates)
    converted = [convert(row) for row in candidates]
    by_split: dict[str, list[dict]] = defaultdict(list)
    group_split: dict[str, str] = {}
    labels_by_field: dict[str, Counter] = defaultdict(Counter)
    for row in converted:
        group = row["source_group_id"]
        previous = group_split.setdefault(group, row["planned_split"])
        if previous != row["planned_split"]:
            raise ValueError(f"source group leaked across splits: {group}")
        by_split[row["planned_split"]].append(row)
        for field, target in row["targets"].items():
            labels_by_field[field][target["label"]] += 1

    if len(converted) != sum(EXPECTED.values()):
        raise ValueError(f"expected {sum(EXPECTED.values())} records, found {len(converted)}")
    for split, expected in EXPECTED.items():
        if len(by_split[split]) != expected:
            raise ValueError(f"{split}: expected {expected}, found {len(by_split[split])}")

    args.output_dir.mkdir(parents=True, exist_ok=True)
    file_info = {}
    for split in ("train", "dev", "calibration", "test"):
        path = args.output_dir / f"{split}.jsonl"
        sha256 = write_jsonl(path, by_split[split])
        file_info[f"{split}.jsonl"] = {
            "records": len(by_split[split]),
            "decisions": len(by_split[split]) * 5,
            "bytes": path.stat().st_size,
            "sha256": sha256,
        }

    manifest = {
        "dataset": "ShareGPT Chinese Laya typed-decision v2",
        "source_dataset": "AI-ModelScope/sharegpt_gpt4",
        "source_url": "https://modelscope.cn/datasets/AI-ModelScope/sharegpt_gpt4",
        "source_candidates": str(args.candidates),
        "source_candidate_sha256": hashlib.sha256(args.candidates.read_bytes()).hexdigest(),
        "source_license_note": "ModelScope card displays CC-BY-4.0; verify upstream ShareGPT terms before redistribution.",
        "label_source": "DeepSeek Flash, 3 independent votes per decision; majority vote with stable policy-order tie break.",
        "human_review": "pending for all candidate decisions; pseudo-labels are not human gold.",
        "split_unit": "source_group_id",
        "split_sizes": EXPECTED,
        "counts_by_field_and_label": {key: dict(value) for key, value in labels_by_field.items()},
        "files": file_info,
        "note": "Only train.jsonl is used for optimization. dev.jsonl is retained but was not used for checkpoint selection in this run; calibration.jsonl is used only for scalar temperature fitting. Existing Laya has already evaluated test.jsonl, so this comparison is not a fresh blind test.",
    }
    manifest_path = args.output_dir / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"records": len(converted), "decisions": len(converted) * 5,
                      "groups": len(group_split), "files": file_info,
                      "manifest": str(manifest_path)}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
