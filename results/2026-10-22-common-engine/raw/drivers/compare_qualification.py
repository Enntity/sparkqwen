#!/usr/bin/env python3
# SPDX-License-Identifier: AGPL-3.0-only
"""Compare private SparkQwen benchmark and qualification receipts.

The baseline is ``baseline/bench-baseline.json``.  Future runs can be placed in
``strict/bench-strict.json`` and ``spark/bench-spark.json`` or supplied with
``--candidate MODE=PATH``.  Inputs are read only; the output contains normalized
repetition rows, medians, descriptive speed deltas, and links plus hashes for
the untouched raw receipts.

Warm conversations are summarized by size and turn, but their speed deltas are
explicitly descriptive.  This tool never claims that warm requests matched by
position; that requires request hashes in both bench files.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import statistics
from typing import Any, Iterable


HERE = Path(__file__).resolve().parent
CELL_ORDER = ("decode", "prefill", "conc", "warm")


def read_json(path: Path) -> Any:
    return json.loads(path.read_text())


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def number(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    return None


def median(values: Iterable[Any]) -> float | None:
    numeric = [value for value in (number(item) for item in values) if value is not None]
    return statistics.median(numeric) if numeric else None


def json_number(value: float | None) -> int | float | None:
    if value is None:
        return None
    return int(value) if value.is_integer() else value


def row_values(row: dict[str, Any], key: str) -> list[float]:
    value = row.get(key)
    if isinstance(value, list):
        return [item for item in (number(item) for item in value) if item is not None]
    item = number(value)
    return [] if item is None else [item]


def row_speed(cell: str, row: dict[str, Any]) -> float | None:
    key = "agg_tok_s" if cell == "conc" else "tok_s"
    return number(row.get(key))


def row_ttft(row: dict[str, Any]) -> float | None:
    return median(row_values(row, "ttft"))


def group_descriptor(cell: str, row: dict[str, Any]) -> tuple[Any, ...]:
    if cell == "decode":
        return (row.get("kind", "unknown"),)
    if cell == "prefill":
        return (row.get("size", "unknown"),)
    if cell == "conc":
        return (row.get("c", "unknown"),)
    # Keep warm turns separate.  A cold turn and a cached continuation have
    # different workloads even when they share a context-size label.
    return (row.get("size", "unknown"), row.get("turn", "unknown"))


def descriptor_label(cell: str, descriptor: tuple[Any, ...]) -> str:
    if cell == "decode":
        return str(descriptor[0])
    if cell == "prefill":
        return f"{descriptor[0]} tokens"
    if cell == "conc":
        return f"{descriptor[0]} streams"
    return f"{descriptor[0]} tokens / turn {descriptor[1]}"


def descriptor_sort_key(descriptor: tuple[Any, ...]) -> tuple[tuple[int, float | str], ...]:
    result: list[tuple[int, float | str]] = []
    for value in descriptor:
        numeric = number(value)
        result.append((0, numeric) if numeric is not None else (1, str(value)))
    return tuple(result)


def numeric_medians(rows: list[dict[str, Any]]) -> dict[str, int | float]:
    keys = sorted({key for row in rows for key, value in row.items()
                   if number(value) is not None})
    return {key: json_number(median(row.get(key) for row in rows)) for key in keys}


def summarize_bench(path: Path, mode: str) -> dict[str, Any]:
    data = read_json(path)
    cells = data.get("cells")
    if not isinstance(cells, dict):
        raise ValueError(f"{path} has no cells object")
    result: dict[str, Any] = {
        "arm": data.get("arm", mode),
        "date": data.get("date"),
        "source": {"path": str(path), "sha256": sha256(path)},
        "cells": {},
    }
    for cell in CELL_ORDER:
        rows = cells.get(cell, [])
        if not isinstance(rows, list):
            raise ValueError(f"{path}: cells.{cell} is not a list")
        grouped: dict[str, dict[str, Any]] = {}
        descriptors: dict[str, tuple[Any, ...]] = {}
        for row in rows:
            if not isinstance(row, dict):
                raise ValueError(f"{path}: cells.{cell} contains a non-object row")
            descriptor = group_descriptor(cell, row)
            key = json.dumps(descriptor, separators=(",", ":"), ensure_ascii=False)
            if key not in grouped:
                grouped[key] = {"label": descriptor_label(cell, descriptor),
                                "descriptor": list(descriptor), "repetitions": []}
                descriptors[key] = descriptor
            grouped[key]["repetitions"].append(dict(row))
        buckets: list[dict[str, Any]] = []
        for key in sorted(grouped, key=lambda item: descriptor_sort_key(descriptors[item])):
            bucket = grouped[key]
            repetitions = bucket["repetitions"]
            speeds = [value for value in (row_speed(cell, row) for row in repetitions)
                      if value is not None]
            ttfts = [value for row in repetitions for value in row_values(row, "ttft")]
            walls = [value for value in (number(row.get("wall")) for row in repetitions)
                     if value is not None]
            bucket["count"] = len(repetitions)
            bucket["medians"] = {
                "speed_tok_s": json_number(median(speeds)),
                "ttft_s": json_number(median(ttfts)),
                "wall_s": json_number(median(walls)),
                "numeric_fields": numeric_medians(repetitions),
            }
            bucket["request_hashes"] = [row["request_sha256"]
                                         for row in repetitions
                                         if isinstance(row.get("request_sha256"), str)]
            buckets.append(bucket)
        result["cells"][cell] = buckets
    return result


def bucket_map(bench: dict[str, Any], cell: str) -> dict[str, dict[str, Any]]:
    return {json.dumps(bucket["descriptor"], separators=(",", ":"), ensure_ascii=False): bucket
            for bucket in bench.get("cells", {}).get(cell, [])}


def request_match(baseline: dict[str, Any], candidate: dict[str, Any]) -> bool:
    left = baseline.get("request_hashes", [])
    right = candidate.get("request_hashes", [])
    return bool(left) and left == right and len(left) == baseline.get("count") == candidate.get("count")


def delta_percent(candidate: float | None, baseline: float | None) -> float | None:
    if candidate is None or baseline in (None, 0):
        return None
    return (candidate / baseline - 1.0) * 100.0


def compare_bench(baseline: dict[str, Any], candidate: dict[str, Any], mode: str) -> list[dict[str, Any]]:
    comparisons: list[dict[str, Any]] = []
    for cell in CELL_ORDER:
        left = bucket_map(baseline, cell)
        right = bucket_map(candidate, cell)
        for key in sorted(set(left) | set(right)):
            base = left.get(key)
            cand = right.get(key)
            base_speed = base.get("medians", {}).get("speed_tok_s") if base else None
            cand_speed = cand.get("medians", {}).get("speed_tok_s") if cand else None
            matched = bool(base and cand and request_match(base, cand))
            warm = cell == "warm"
            comparisons.append({
                "mode": mode,
                "cell": cell,
                "label": (cand or base)["label"],
                "baseline_repetitions": base.get("count") if base else 0,
                "candidate_repetitions": cand.get("count") if cand else 0,
                "baseline_median_tok_s": base_speed,
                "candidate_median_tok_s": cand_speed,
                "speed_delta_pct": json_number(delta_percent(cand_speed, base_speed)),
                "request_match_verified": matched,
                "comparison_basis": (
                    "descriptive_unpaired_warm_median"
                    if warm and not matched else
                    "request_hashes_equal" if matched else
                    "same_bench_cell_without_request_hash_proof"
                ),
                "warm_request_match_claim": matched if warm else None,
            })
    return comparisons


def first_file(paths: Iterable[Path]) -> Path | None:
    for path in paths:
        if path.is_file():
            return path
    return None


def analysis_sources(bench_path: Path) -> dict[str, Path | None]:
    directory = bench_path.parent
    return {
        "analysis": first_file((directory / "analysis.json",
                                 directory / "qualification" / "analysis.json")),
        "corrected_summary": first_file((directory / "corrected" / "summary.corrected.json",
                                          directory / "qualification" / "corrected" / "summary.corrected.json")),
        "qualification_summary": first_file((directory / "qualification" / "summary.json",
                                              directory / "summary.json")),
        "xml": first_file((directory / "xml" / "summary.json",
                            directory / "qualification" / "xml" / "summary.json")),
    }


def analysis_data(sources: dict[str, Path | None]) -> tuple[dict[str, Any], dict[str, str]]:
    loaded: dict[str, Any] = {}
    paths: dict[str, str] = {}
    for name, path in sources.items():
        if path is not None:
            loaded[name] = read_json(path)
            paths[name] = str(path)
    return loaded, paths


def metric_source(loaded: dict[str, Any], key: str) -> tuple[Any, str | None]:
    for name in ("analysis", "corrected_summary", "qualification_summary"):
        data = loaded.get(name)
        if not isinstance(data, dict):
            continue
        if key in data:
            return data[key], name
        results = data.get("results")
        if isinstance(results, dict) and key in results:
            return results[key], name
    return None, None


def summarize_correctness(bench_path: Path, mode: str) -> dict[str, Any]:
    sources = analysis_sources(bench_path)
    loaded, paths = analysis_data(sources)
    nll, nll_source = metric_source(loaded, "canonical_nll")
    if isinstance(nll, dict):
        canonical_nll = {
            "nll_nats_per_token": nll.get("nll_nats_per_token"),
            "protocol_ok": nll.get("protocol_ok"),
            "status": nll.get("status"),
            "score_positions": nll.get("score_positions"),
            "semantic_ok": nll.get("semantic_ok"),
            "engine_signal": nll.get("engine_signal"),
            "source": nll_source,
        }
    else:
        canonical_nll = {"nll_nats_per_token": None, "source": None}

    parity, parity_source = metric_source(loaded, "decoded_parity")
    if not isinstance(parity, list):
        greedy, greedy_source = metric_source(loaded, "greedy")
        if isinstance(greedy, dict):
            parity = list(greedy.get("comparisons") or [])
            serial = greedy.get("serial_vs_mtp")
            if isinstance(serial, dict):
                parity.append(serial)
            parity_source = greedy_source
        else:
            parity = []
    parity_rows = []
    for item in parity:
        if not isinstance(item, dict):
            continue
        details = item.get("details")
        if isinstance(details, list):
            # qualification.py compares usage as well as decoded fields.  A
            # usage-counter difference is useful evidence, but it is not a
            # decoded-output mismatch; match analyze_qualification.py's
            # parity contract when analysis.json is unavailable.
            decoded_fields = ("reasoning_content", "content", "tool_calls", "finish_reason")
            protocol_details = [detail for detail in details
                                if isinstance(detail, dict) and detail.get("protocol_ok")]
            field_matches = {
                field: sum(bool((detail.get("fields") or {}).get(field))
                           for detail in protocol_details)
                for field in decoded_fields
            }
            decoded_matched = sum(all((detail.get("fields") or {}).get(field)
                                      for field in decoded_fields)
                                  for detail in protocol_details)
            item = {**item,
                    "matched": decoded_matched,
                    "total": item.get("total") or len(protocol_details),
                    "field_matches": field_matches}
        parity_rows.append({
            "left": item.get("left"), "right": item.get("right"),
            "matched": item.get("matched"), "total": item.get("total"),
            "field_matches": item.get("field_matches"),
            "mismatches": item.get("mismatches", []),
        })
    decoded_parity = {
        "pairs": parity_rows,
        "all_pairs_match": bool(parity_rows) and all(row.get("matched") == row.get("total")
                                                     for row in parity_rows),
        "source": parity_source,
    }

    retrieval, retrieval_source = metric_source(loaded, "retrieval_content")
    if isinstance(retrieval, dict):
        long_content = {
            "correct": retrieval.get("correct"), "total": retrieval.get("total"),
            "failures": retrieval.get("failures", []), "source": retrieval_source,
        }
    else:
        long_summary, long_source = metric_source(loaded, "long_context")
        if isinstance(long_summary, dict):
            long_content = {
                "correct": long_summary.get("semantic_correct"),
                "total": long_summary.get("semantic_total"),
                "failures": [row for row in long_summary.get("rows", [])
                             if isinstance(row, dict) and row.get("semantic_ok") is False],
                "source": long_source,
                "ground_truth_rescored": long_source == "corrected_summary",
            }
        else:
            long_content = {"correct": None, "total": None, "failures": [], "source": None}

    xml = loaded.get("xml")
    xml_rows = xml if isinstance(xml, list) else xml.get("rows", []) if isinstance(xml, dict) else []
    if isinstance(xml_rows, list):
        valid_rows = [row for row in xml_rows if isinstance(row, dict)]
        real_rows = [row for row in valid_rows if "real" in str(row.get("case", ""))]
        xml32 = {
            "ok": sum(bool(row.get("ok")) for row in valid_rows),
            "total": len(valid_rows),
            "real_controls_ok": sum(bool(row.get("ok")) for row in real_rows),
            "real_controls_total": len(real_rows),
            "source": paths.get("xml"),
        }
    else:
        xml32 = {"ok": None, "total": None, "real_controls_ok": None,
                 "real_controls_total": None, "source": None}

    return {
        "mode": mode,
        "sources": paths,
        "canonical_nll": canonical_nll,
        "decoded_parity": decoded_parity,
        "long_final_content": long_content,
        "xml32": xml32,
    }


def load_arm(bench_path: Path, mode: str) -> dict[str, Any]:
    bench = summarize_bench(bench_path, mode)
    bench["correctness"] = summarize_correctness(bench_path, mode)
    return bench


def markdown_number(value: Any, digits: int = 2) -> str:
    if value is None:
        return "—"
    return f"{float(value):.{digits}f}"


def markdown_delta(value: Any, warm: bool) -> str:
    if value is None:
        return "—"
    suffix = "*" if warm else ""
    return f"{float(value):+.2f}%{suffix}"


def correctness_cell(value: dict[str, Any], key: str) -> str:
    if key == "nll":
        return markdown_number(value.get("canonical_nll", {}).get("nll_nats_per_token"), 6)
    if key == "parity":
        pairs = value.get("decoded_parity", {}).get("pairs", [])
        return "; ".join(f"{p.get('left')}↔{p.get('right')} {p.get('matched')}/{p.get('total')}"
                          for p in pairs) or "—"
    if key == "long":
        item = value.get("long_final_content", {})
        correct, total = item.get("correct"), item.get("total")
        return f"{correct}/{total}" if correct is not None and total is not None else "—"
    item = value.get("xml32", {})
    if item.get("total") is None:
        return "—"
    return f"{item.get('ok')}/{item.get('total')} (real {item.get('real_controls_ok')}/{item.get('real_controls_total')})"


def render_markdown(report: dict[str, Any]) -> str:
    baseline = report["arms"]["baseline"]
    candidates = [(mode, arm) for mode, arm in report["arms"].items() if mode != "baseline"]
    lines = ["# SparkQwen qualification comparison", "",
             f"Baseline: `{baseline['source']['path']}`  ",
             f"SHA-256: `{baseline['source']['sha256']}`", "",
             "## Benchmark medians", "",
             "| cell | arm | repetitions | median tok/s | delta vs baseline | median TTFT (s) | median wall (s) |",
             "|---|---|---:|---:|---:|---:|---:|"]
    rows = []
    for mode, arm in [("baseline", baseline), *candidates]:
        for cell in CELL_ORDER:
            for bucket in arm["cells"].get(cell, []):
                comparison = next((item for item in report["bench_comparisons"]
                                   if item["mode"] == mode and item["cell"] == cell
                                   and item["label"] == bucket["label"]), None)
                rows.append((cell, mode, bucket, comparison))
    for cell, mode, bucket, comparison in rows:
        delta = None if mode == "baseline" else comparison.get("speed_delta_pct")
        lines.append("| {cell} / {label} | {mode} | {count} | {speed} | {delta} | {ttft} | {wall} |".format(
            cell=cell, label=bucket["label"], mode=mode,
            count=bucket["count"], speed=markdown_number(bucket["medians"].get("speed_tok_s")),
            delta="—" if mode == "baseline" else markdown_delta(delta, cell == "warm"),
            ttft=markdown_number(bucket["medians"].get("ttft_s")),
            wall=markdown_number(bucket["medians"].get("wall_s"))))
    lines += ["", "*Warm-conversation deltas are descriptive unpaired medians; no matched-request claim is made unless request hashes are present and equal.", "",
              "## Correctness receipts", "",
              "| arm | canonical NLL | decoded parity | long final-content | XML32 |", "|---|---:|---|---:|---:|"]
    for mode, arm in [("baseline", baseline), *candidates]:
        correctness = arm["correctness"]
        lines.append(f"| {mode} | {correctness_cell(correctness, 'nll')} | {correctness_cell(correctness, 'parity')} | {correctness_cell(correctness, 'long')} | {correctness_cell(correctness, 'xml')} |")
    lines += ["", "Raw inputs are preserved in place; this report records their paths and SHA-256 values without rewriting them.", ""]
    return "\n".join(lines)


def parse_candidate(value: str) -> tuple[str, Path]:
    if "=" not in value:
        raise argparse.ArgumentTypeError("candidate must be MODE=PATH")
    mode, raw_path = value.split("=", 1)
    if not mode or not raw_path:
        raise argparse.ArgumentTypeError("candidate must be MODE=PATH")
    return mode, Path(raw_path)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=HERE)
    parser.add_argument("--baseline", type=Path)
    parser.add_argument("--candidate", action="append", type=parse_candidate,
                        metavar="MODE=PATH", help="candidate bench JSON; may be repeated")
    parser.add_argument("--out-json", type=Path)
    parser.add_argument("--out-md", type=Path)
    args = parser.parse_args()
    root = args.root.resolve()
    baseline_path = (args.baseline or root / "baseline" / "bench-baseline.json").resolve()
    if not baseline_path.is_file():
        raise SystemExit(f"missing baseline bench JSON: {baseline_path}")
    candidates = list(args.candidate or [])
    if not candidates:
        for mode in ("strict", "spark"):
            path = root / mode / f"bench-{mode}.json"
            if path.is_file():
                candidates.append((mode, path))
    arms = {"baseline": load_arm(baseline_path, "baseline")}
    for mode, path in candidates:
        path = path if path.is_absolute() else (root / path)
        path = path.resolve()
        if not path.is_file():
            raise SystemExit(f"missing {mode} candidate bench JSON: {path}")
        if mode in arms:
            raise SystemExit(f"duplicate arm: {mode}")
        arms[mode] = load_arm(path, mode)
    report = {
        "schema": "sparkqwen.qualification-comparison/v1",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "baseline_mode": "baseline",
        "arms": arms,
        "bench_comparisons": [],
    }
    for mode in arms:
        if mode != "baseline":
            report["bench_comparisons"].extend(compare_bench(arms["baseline"], arms[mode], mode))
    out_json = (args.out_json or root / "qualification-comparison.json").resolve()
    out_md = (args.out_md or root / "qualification-comparison.md").resolve()
    out_json.parent.mkdir(parents=True, exist_ok=True)
    out_md.parent.mkdir(parents=True, exist_ok=True)
    out_json.write_text(json.dumps(report, indent=2, ensure_ascii=False, sort_keys=True) + "\n")
    out_md.write_text(render_markdown(report))
    print(json.dumps({"json": str(out_json), "markdown": str(out_md),
                      "candidates": [mode for mode in arms if mode != "baseline"]}, indent=2))


if __name__ == "__main__":
    main()
