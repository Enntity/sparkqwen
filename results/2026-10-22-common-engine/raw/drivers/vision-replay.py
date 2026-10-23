#!/usr/bin/env python3
# SPDX-License-Identifier: AGPL-3.0-only
"""Replay the archived Qwen vision checks against a running server.

The request bodies are copied byte-for-byte from the archived fidelity review.
The archived source is never modified. Each replay writes its request,
response, headers, status, hashes, elapsed time, and semantic grade under
``--out/raw``. Use ``--offline`` to validate the fixtures and grader without
making HTTP calls.

Example::

    python3 experiments/qwen-common-20261022/vision-replay.py \
      --url http://localhost:8893 \
      --evidence-root /path/to/2026-10-20-fidelity-review \
      --out /path/to/vision-replay
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Any


CASES: tuple[dict[str, Any], ...] = (
    {
        "name": "vision-a5",
        "request": "raw/quality/vision-original/http/0003-vision-a5/request.body",
        "response": "raw/quality/vision-original/http/0003-vision-a5/response.body",
        "receipt": "raw/quality/vision-original/http/0003-vision-a5/receipt.json",
        "status": 200,
        "request_sha256": "8e22d1eec7d2871b9074a0baf09327d8947c9ac1798aeab2e040501f7a74498f",
        "response_sha256": "517c5e9b7bd7f008181da4d9b5b5daa16cf58e05befe8a44366b663a4624fb81",
        "expected_lines": (
            "red circle",
            "blue square",
            "green triangle",
            "orange circle",
            "purple square",
        ),
    },
    {
        "name": "vision-b16680",
        "request": "raw/quality/vision-original/http/0004-vision-b16680/request.body",
        "response": "raw/quality/vision-original/http/0004-vision-b16680/response.body",
        "receipt": "raw/quality/vision-original/http/0004-vision-b16680/receipt.json",
        "status": 200,
        "request_sha256": "d456be971d3c25600d28cf992a92e83bbd94f239581b72d2b6bb0634954ddf3a",
        "response_sha256": "28c1cb0cf7e616347bf44bb00f8ac5d8ec2047b8d6701e5da7a2703b32ce9dd8",
        # The original grader expected a square. The frozen image is a
        # rectangle, so this is the corrected expectation.
        "expected_lines": (
            "red circle",
            "blue square",
            "green triangle",
            "orange circle",
            "purple rectangle",
        ),
    },
    {
        "name": "vision-d8",
        "request": "raw/quality/remaining/http/0003-vision-d8/request.body",
        "response": "raw/quality/remaining/http/0003-vision-d8/response.body",
        "receipt": "raw/quality/remaining/http/0003-vision-d8/receipt.json",
        "status": 200,
        "request_sha256": "0b7c9c1fddfbaae4edcdb29cf4819a744d7471b006890cef55ebdcb2e81ddef5",
        "response_sha256": "a2fe82f4fe39c04f607b2f6e0f2c78bba8f3d51c818eea0f5e09491261b1596a",
        "expected_lines": (
            "red circle",
            "blue square",
            "green triangle",
            "orange circle",
            "purple square",
            "black triangle",
            "yellow circle",
            "pink square",
        ),
    },
    {
        "name": "vision-admission-corrected",
        "request": "raw/quality/admission-corrected/request.body",
        "response": "raw/quality/admission-corrected/response.body",
        "receipt": "raw/quality/admission-corrected/receipt.json",
        "result": "raw/quality/admission-corrected/result.json",
        "status": 400,
        "request_sha256": "5179e83383d6e0226600397ef1738a869db3c7949ed3dbf02845bca6b813db3b",
        "response_sha256": "f40dc5008b0762b17553faa940a225170fc27f61beb3e4d02493cd786239bdb4",
        "error_code": "vision_input_too_large",
    },
)


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True, ensure_ascii=False) + "\n")


def safe_url(value: str) -> str:
    parsed = urllib.parse.urlsplit(value)
    host = parsed.hostname or ""
    if parsed.port:
        host += f":{parsed.port}"
    return urllib.parse.urlunsplit((parsed.scheme, host, parsed.path, "", ""))


def completion_url(value: str) -> str:
    """Accept either a server base URL or an OpenAI completion endpoint."""
    value = value.rstrip("/")
    path = urllib.parse.urlsplit(value).path.rstrip("/")
    if path.endswith("/v1/chat/completions") or path.endswith("/chat/completions"):
        return value
    if path.endswith("/v1"):
        return value + "/chat/completions"
    return value + "/v1/chat/completions"


def iso_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def normalized_lines(value: Any) -> list[str] | None:
    if not isinstance(value, str):
        return None
    return [line.strip() for line in value.replace("\r\n", "\n").split("\n") if line.strip()]


def grade(spec: dict[str, Any], status: int | None, raw: bytes) -> dict[str, Any]:
    try:
        obj = json.loads(raw)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        return {"passed": False, "json_error": str(exc), "status": status}

    if spec["status"] == 200:
        try:
            choice = obj["choices"][0]
            message = choice["message"]
            content = message.get("content")
            got = normalized_lines(content)
            expected = list(spec["expected_lines"])
            passed = status == 200 and choice.get("finish_reason") == "stop" and got == expected
            return {
                "passed": passed,
                "status": status,
                "finish_reason": choice.get("finish_reason"),
                "content": content,
                "normalized_lines": got,
                "expected_lines": expected,
            }
        except (KeyError, IndexError, TypeError) as exc:
            return {"passed": False, "status": status, "response_shape_error": str(exc)}

    error = obj.get("error") if isinstance(obj, dict) else None
    error_code = error.get("code") if isinstance(error, dict) else None
    completion_observed = isinstance(obj, dict) and ("choices" in obj or "usage" in obj)
    return {
        "passed": status == 400 and error_code == spec["error_code"] and not completion_observed,
        "status": status,
        "error_code": error_code,
        "error_message": error.get("message") if isinstance(error, dict) else None,
        "expected_error_code": spec["error_code"],
        "completion_observed": completion_observed,
    }


def archive_info(evidence_root: Path, spec: dict[str, Any]) -> tuple[bytes, bytes, dict[str, Any]]:
    request_path = evidence_root / spec["request"]
    response_path = evidence_root / spec["response"]
    receipt_path = evidence_root / spec["receipt"]
    request = request_path.read_bytes()
    response = response_path.read_bytes()
    if sha256(request) != spec["request_sha256"]:
        raise ValueError(f"{spec['name']}: archived request hash changed")
    if sha256(response) != spec["response_sha256"]:
        raise ValueError(f"{spec['name']}: archived response hash changed")
    receipt = json.loads(receipt_path.read_text())
    if receipt.get("request_sha256") not in (None, spec["request_sha256"]):
        raise ValueError(f"{spec['name']}: archived receipt request hash differs")
    if receipt.get("response_sha256") not in (None, spec["response_sha256"]):
        raise ValueError(f"{spec['name']}: archived receipt response hash differs")
    if receipt.get("status") not in (None, spec["status"]):
        raise ValueError(f"{spec['name']}: archived receipt status differs")

    elapsed_ms = None
    if receipt.get("started_ns") is not None and receipt.get("finished_ns") is not None:
        elapsed_ms = round((receipt["finished_ns"] - receipt["started_ns"]) / 1_000_000, 3)
    archive = {
        "request_source": spec["request"],
        "response_source": spec["response"],
        "receipt_source": spec["receipt"],
        "request_bytes": len(request),
        "request_sha256": spec["request_sha256"],
        "response_bytes": len(response),
        "response_sha256": spec["response_sha256"],
        "status": spec["status"],
        "elapsed_ms": elapsed_ms,
        "response_headers": receipt.get("response_headers", {}),
        "stage": receipt.get("stage"),
    }
    if "result" in spec:
        result_path = evidence_root / spec["result"]
        result = json.loads(result_path.read_text())
        archive["result_source"] = spec["result"]
        archive["result"] = {
            key: result.get(key)
            for key in ("passed", "scope", "request_sha256", "response_sha256")
            if key in result
        }
    archive_grade = grade(spec, spec["status"], response)
    if not archive_grade["passed"]:
        raise ValueError(f"{spec['name']}: archived response fails corrected grade: {archive_grade}")
    archive["grade"] = archive_grade
    return request, response, archive


def replay_case(
    spec: dict[str, Any],
    request: bytes,
    archived_response: bytes,
    archive: dict[str, Any],
    endpoint: str,
    out: Path,
    timeout: float,
    offline: bool,
) -> dict[str, Any]:
    case_dir = out / "raw" / spec["name"]
    case_dir.mkdir(parents=True, exist_ok=True)
    (case_dir / "request.body").write_bytes(request)

    started_at = iso_now()
    started_ns = time.time_ns()
    start_mono = time.monotonic_ns()
    status: int | None = None
    response_headers: dict[str, str] = {}
    response = b""
    error: str | None = None
    if offline:
        status = spec["status"]
        response = archived_response
        response_headers = dict(archive.get("response_headers") or {})
    else:
        headers = {"Content-Type": "application/json", "Content-Length": str(len(request))}
        try:
            req = urllib.request.Request(endpoint, data=request, headers=headers, method="POST")
            with urllib.request.urlopen(req, timeout=timeout) as reply:
                status = reply.status
                response_headers = {str(key).lower(): str(value) for key, value in reply.headers.items()}
                response = reply.read()
        except urllib.error.HTTPError as exc:
            status = exc.code
            response_headers = {str(key).lower(): str(value) for key, value in exc.headers.items()}
            response = exc.read()
            error = f"HTTP {exc.code}"
        except Exception as exc:  # Preserve a failed transport as evidence for all cases.
            error = f"{type(exc).__name__}: {exc}"
    finished_ns = time.time_ns()
    elapsed_ms = round((time.monotonic_ns() - start_mono) / 1_000_000, 3)
    finished_at = iso_now()
    (case_dir / "response.body").write_bytes(response)
    grading = grade(spec, status, response)
    receipt = {
        "case": spec["name"],
        "path": "/v1/chat/completions",
        "url": safe_url(endpoint),
        "offline": offline,
        "started_at": started_at,
        "finished_at": finished_at,
        "started_ns": started_ns,
        "finished_ns": finished_ns,
        "elapsed_ms": elapsed_ms if not offline else archive.get("elapsed_ms"),
        "status": status,
        "response_headers": response_headers,
        "request_bytes": len(request),
        "request_sha256": sha256(request),
        "response_bytes": len(response),
        "response_sha256": sha256(response),
        "error": error,
        "grade": grading,
        "archive": archive,
    }
    write_json(case_dir / "receipt.json", receipt)
    return receipt


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", required=True, help="server base URL or /v1/chat/completions endpoint")
    parser.add_argument("--evidence-root", required=True, type=Path,
                        help="archived 2026-10-20-fidelity-review directory")
    parser.add_argument("--out", required=True, type=Path,
                        help="fresh output directory for replay evidence")
    parser.add_argument("--timeout", type=float, default=900.0,
                        help="per-request HTTP timeout in seconds (default: 900)")
    parser.add_argument("--offline", action="store_true",
                        help="grade archived responses without making HTTP calls")
    args = parser.parse_args(argv)

    evidence_root = args.evidence_root.resolve()
    out = args.out.resolve()
    if not evidence_root.is_dir():
        raise SystemExit(f"evidence root is not a directory: {evidence_root}")
    if out.exists() and any(out.iterdir()):
        raise SystemExit(f"output directory must be fresh: {out}")
    out.mkdir(parents=True, exist_ok=True)
    endpoint = completion_url(args.url)

    loaded: list[tuple[dict[str, Any], bytes, bytes, dict[str, Any]]] = []
    for spec in CASES:
        request, response, archive = archive_info(evidence_root, spec)
        loaded.append((spec, request, response, archive))

    receipts = [
        replay_case(spec, request, response, archive, endpoint, out, args.timeout, args.offline)
        for spec, request, response, archive in loaded
    ]
    summary = {
        "script": "vision-replay.py",
        "offline": args.offline,
        "url": safe_url(endpoint),
        "evidence_root": str(evidence_root),
        "cases": receipts,
        "passed": all(receipt["grade"].get("passed") for receipt in receipts),
        "scope": "Archived a5, corrected b16680, d8, and corrected oversized-header admission request",
        "live_calls": 0 if args.offline else len(receipts),
    }
    write_json(out / "summary.json", summary)
    print(json.dumps({"passed": summary["passed"], "out": str(out),
                      "live_calls": summary["live_calls"],
                      "cases": {r["case"]: r["grade"].get("passed") for r in receipts}},
                   sort_keys=True))
    return 0 if summary["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
