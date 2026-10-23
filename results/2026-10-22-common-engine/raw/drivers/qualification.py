#!/usr/bin/env python3
# SPDX-License-Identifier: AGPL-3.0-only
"""CPU-side SparkQwen qualification driver.

This driver owns no server, containers, GPUs, credentials, or model files. It
copies the exact request fixtures preserved by the Qwen fidelity review into
the requested output directory, then (unless ``--offline`` is given) sends
those bodies to a running HTTP server. Every request and response body is
retained under ``raw/``. Model-choice mistakes are recorded as semantic
observations and are never converted into engine failures. The greedy serial
control uses the same server with ``disable_mtp=true`` by default; passing
``--serial-url`` selects a separately configured serial server instead. For
the same-server control, the exact baseline body and the one-field mutation
metadata are retained next to the sent request.
"""

from __future__ import annotations

import argparse
import concurrent.futures
import hashlib
import json
import math
import os
from pathlib import Path
import re
import shutil
import time
from typing import Any
import urllib.error
import urllib.parse
import urllib.request

HERE = Path(__file__).resolve().parent
RESEARCH = HERE.parent.parent
DEFAULT_EVIDENCE = (RESEARCH / "worktrees" / "sparkqwen-fidelity-rc-20261019" /
                    "results" / "2026-10-20-fidelity-review")
DEFAULT_URL = "http://localhost:8893"
DEFAULT_MODEL = "qwen3.8-flash-next-atlas"
MODES = ("baseline", "strict", "spark", "tp1")
COMPARE_FIELDS = ("reasoning_content", "content", "tool_calls", "finish_reason", "usage")
EXPECTED_TOOL_ARGS = {"city": "Paris"}

# The seeded needle fixture is deliberately a plain-text lookup task.  Keep
# the parser here instead of trusting the recorder's arrival order: concurrent
# requests can be observed in a different order from the JSONL metadata.
NEEDLE_A_RE = re.compile(r"^k(?P<key>\d{6}) -> c(?P<code>\d{6})$", re.MULTILINE)
NEEDLE_B_RE = re.compile(r"^c(?P<code>\d{6}) = (?P<value>\d{8})$", re.MULTILINE)
NEEDLE_QUERY_RE = re.compile(
    r"Find the code for key k(?P<key>\d{6}) in Table A, then that code's value in Table B\."
)
EIGHT_DIGITS_RE = re.compile(r"\d{8}\Z")


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def compact_sha(value: Any) -> str:
    return sha256(json.dumps(value, separators=(",", ":"), ensure_ascii=False).encode())


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True, ensure_ascii=False) + "\n")


def read_json(path: Path) -> Any:
    return json.loads(path.read_text())


def json_bytes(value: Any) -> bytes:
    return (json.dumps(value, indent=2, sort_keys=True, ensure_ascii=False) + "\n").encode()


def needle_ground_truth(request: dict[str, Any]) -> dict[str, Any]:
    """Derive one seeded lookup answer from the request text.

    The preserved expected JSONL is metadata from the original recorder.  Its
    first three rows are in a different order from the sorted request paths,
    so it is unsafe to zip those rows to request directories.  Requiring the
    queried key and its two lookup legs to be unambiguous catches malformed or
    accidentally altered fixtures while allowing unrelated random code
    collisions elsewhere in the large tables.
    """
    messages = request.get("messages")
    if not isinstance(messages, list):
        raise ValueError("needle request has no messages list")
    user_contents = [message.get("content") for message in messages
                     if isinstance(message, dict) and message.get("role") == "user"
                     and isinstance(message.get("content"), str)]
    if len(user_contents) != 1:
        raise ValueError("needle request must contain exactly one textual user message")
    content = user_contents[0]
    table_a = [(match.group("key"), match.group("code"))
               for match in NEEDLE_A_RE.finditer(content)]
    table_b = [(match.group("code"), match.group("value"))
               for match in NEEDLE_B_RE.finditer(content)]
    query_matches = list(NEEDLE_QUERY_RE.finditer(content))
    if not table_a or not table_b or len(query_matches) != 1:
        raise ValueError("needle request does not contain the expected tables and query")
    if len(table_a) != len(table_b):
        raise ValueError("needle tables contain different numbers of entries")
    if len(set(table_a)) != len(table_a) or len(set(table_b)) != len(table_b):
        raise ValueError("needle table contains a duplicate entry")
    if len({key for key, _ in table_a}) != len(table_a):
        raise ValueError("needle Table A contains a duplicate key")

    key = query_matches[0].group("key")
    codes = [code for candidate, code in table_a if candidate == key]
    if len(codes) != 1:
        raise ValueError(f"needle query key k{key} is not unique")
    code = codes[0]
    values = [value for candidate, value in table_b if candidate == code]
    if len(values) != 1:
        raise ValueError(f"needle query code c{code} is not unique in Table B")
    answer = values[0]
    if not EIGHT_DIGITS_RE.fullmatch(answer):
        raise ValueError(f"needle answer is not an 8-digit value: {answer!r}")
    return {"key": key, "code": code, "answer": answer,
            "table_a_entries": len(table_a), "table_b_entries": len(table_b),
            "table_b_distinct_codes": len({candidate for candidate, _ in table_b}),
            "content_chars": len(content), "content_bytes": len(content.encode())}


def rel_source(path: Path, evidence: Path) -> str:
    try:
        return str(path.relative_to(evidence))
    except ValueError:
        return str(path)


def copy_fixture(source: Path, destination: Path, evidence: Path) -> dict[str, Any]:
    if not source.is_file():
        raise FileNotFoundError(source)
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(source, destination)
    data = destination.read_bytes()
    return {"path": str(destination), "source": rel_source(source, evidence),
            "bytes": len(data), "sha256": sha256(data)}


def endpoint(base: str, path: str) -> str:
    return base.rstrip("/") + path


def safe_url(value: str) -> str:
    """Keep output metadata free of URL userinfo, query strings, and fragments."""
    parsed = urllib.parse.urlsplit(value)
    host = parsed.hostname or ""
    if parsed.port:
        host += f":{parsed.port}"
    return urllib.parse.urlunsplit((parsed.scheme, host, parsed.path, "", ""))


def response_view(obj: dict[str, Any]) -> dict[str, Any]:
    choices = obj.get("choices")
    if not isinstance(choices, list) or len(choices) != 1 or not isinstance(choices[0], dict):
        raise ValueError("OpenAI response has no single choice")
    choice = choices[0]
    message = choice.get("message")
    if not isinstance(message, dict):
        raise ValueError("OpenAI response has no message")
    usage = obj.get("usage") or {}
    return {"reasoning_content": message.get("reasoning_content"),
            "content": message.get("content"), "tool_calls": message.get("tool_calls"),
            "finish_reason": choice.get("finish_reason"),
            "completion_tokens": usage.get("completion_tokens"),
            "prompt_tokens": usage.get("prompt_tokens"), "usage": usage}


def valid_openai_view(view: dict[str, Any], *, require_usage: bool = True) -> bool:
    """Reject an incomplete JSON envelope before any semantic interpretation."""
    if view.get("finish_reason") not in ("stop", "length", "tool_calls", "content_filter"):
        return False
    if not require_usage:
        return True
    return all(isinstance(view.get(key), int) and view[key] >= 0
               for key in ("completion_tokens", "prompt_tokens"))


def text_from_openai(view: dict[str, Any]) -> str:
    return "\n---\n".join(str(view.get(key) or "") for key in ("reasoning_content", "content"))


def answer_in_content(content: Any, answer: str) -> bool:
    """Match a lookup answer only as a complete digit token in final content.

    Reasoning is retained for diagnostics, but it is not the answer channel. A
    digit-boundary check also avoids counting an answer embedded in a longer
    number as a successful retrieval.
    """
    if not isinstance(content, str):
        return False
    return re.search(rf"(?<!\d){re.escape(answer)}(?!\d)", content) is not None


def compare_row_pairs(left_name: str, right_name: str,
                      left_rows: list[dict[str, Any]],
                      right_rows: list[dict[str, Any]]) -> dict[str, Any]:
    details: list[dict[str, Any]] = []
    field_matches = {field: 0 for field in COMPARE_FIELDS}
    protocol_rows = 0
    protocol_failures: list[int] = []
    for left, right in zip(left_rows, right_rows):
        index = left.get("index")
        if not left.get("protocol_ok") or not right.get("protocol_ok"):
            protocol_failures.append(index)
            details.append({"index": index, "protocol_ok": False,
                            "fields": {field: False for field in COMPARE_FIELDS},
                            "exact": False})
            continue
        protocol_rows += 1
        fields = {field: left.get("view", {}).get(field) == right.get("view", {}).get(field)
                  for field in COMPARE_FIELDS}
        field_matches.update({field: field_matches[field] + int(matched)
                              for field, matched in fields.items()})
        details.append({"index": index, "protocol_ok": True, "fields": fields,
                        "exact": all(fields.values())})
    return {"left": left_name, "right": right_name,
            "matched": sum(int(detail["exact"]) for detail in details),
            "total": len(details), "compared_protocol_rows": protocol_rows,
            "protocol_failures": protocol_failures, "field_matches": field_matches,
            "fields": list(COMPARE_FIELDS), "details": details}


def parse_sse(data: bytes) -> list[dict[str, Any]]:
    """Parse SSE framing while retaining event names and JSON data."""
    events: list[dict[str, Any]] = []
    event_name: str | None = None
    data_lines: list[str] = []

    def flush() -> None:
        nonlocal event_name, data_lines
        if event_name is None and not data_lines:
            return
        payload = "\n".join(data_lines)
        row: dict[str, Any] = {"event": event_name, "data_text": payload}
        if payload and payload != "[DONE]":
            try:
                row["data"] = json.loads(payload)
            except json.JSONDecodeError:
                row["data_error"] = True
        events.append(row)
        event_name, data_lines = None, []

    for line in data.decode(errors="replace").splitlines():
        if not line.strip():
            flush()
        elif line.startswith("event:"):
            event_name = line.split(":", 1)[1].strip()
        elif line.startswith("data:"):
            data_lines.append(line.split(":", 1)[1].lstrip())
    flush()
    return events


def openai_stream_view(events: list[dict[str, Any]]) -> dict[str, Any]:
    content: list[str] = []
    reasoning: list[str] = []
    tool_parts: dict[int, dict[str, Any]] = {}
    next_tool_index = 0
    finish: Any = None
    usage: dict[str, Any] = {}
    for event in events:
        data = event.get("data")
        if not isinstance(data, dict):
            continue
        for choice in data.get("choices") or []:
            delta = choice.get("delta") or {}
            if delta.get("content"):
                content.append(str(delta["content"]))
            if delta.get("reasoning_content"):
                reasoning.append(str(delta["reasoning_content"]))
            if delta.get("tool_calls"):
                for raw_tool in delta["tool_calls"]:
                    if not isinstance(raw_tool, dict):
                        continue
                    raw_index = raw_tool.get("index")
                    if isinstance(raw_index, int) and raw_index >= 0:
                        index = raw_index
                        next_tool_index = max(next_tool_index, index + 1)
                    else:
                        index = next_tool_index
                        next_tool_index += 1
                    tool = tool_parts.setdefault(index, {"index": index})
                    for key in ("id", "type"):
                        if raw_tool.get(key) is not None:
                            tool[key] = raw_tool[key]
                    raw_function = raw_tool.get("function")
                    if isinstance(raw_function, dict):
                        function = tool.setdefault("function", {})
                        if raw_function.get("name") is not None:
                            function["name"] = raw_function["name"]
                        if "arguments" in raw_function:
                            function["arguments"] = function.get("arguments", "") + str(
                                raw_function.get("arguments") or "")
            if choice.get("finish_reason") is not None:
                finish = choice["finish_reason"]
        if isinstance(data.get("usage"), dict):
            usage.update(data["usage"])
    tool_calls = [tool_parts[index] for index in sorted(tool_parts)]
    return {"reasoning_content": "".join(reasoning), "content": "".join(content),
            "tool_calls": tool_calls or None, "finish_reason": finish,
            "completion_tokens": usage.get("completion_tokens"),
            "prompt_tokens": usage.get("prompt_tokens"), "usage": usage}


def anthropic_text(obj: dict[str, Any]) -> str:
    return "".join(str(block.get("text") or "") for block in (obj.get("content") or [])
                    if isinstance(block, dict) and block.get("type") == "text")


def anthropic_tools(obj: dict[str, Any]) -> list[dict[str, Any]]:
    return [block for block in (obj.get("content") or [])
            if isinstance(block, dict) and block.get("type") == "tool_use"]


def anthropic_stream_view(events: list[dict[str, Any]]) -> dict[str, Any]:
    text: list[str] = []
    tools: list[dict[str, Any]] = []
    event_names = [str(e.get("event")) for e in events]
    usage: dict[str, Any] = {}
    stop_reason: Any = None
    for event in events:
        data = event.get("data")
        if not isinstance(data, dict):
            continue
        if event.get("event") == "message_start":
            usage.update((data.get("message") or {}).get("usage") or {})
        if event.get("event") == "message_delta":
            usage.update(data.get("usage") or {})
            stop_reason = (data.get("delta") or {}).get("stop_reason", stop_reason)
        if event.get("event") == "content_block_start":
            block = data.get("content_block")
            if isinstance(block, dict) and block.get("type") == "tool_use":
                tools.append(dict(block))
        delta = data.get("delta") or {}
        if delta.get("type") == "text_delta":
            text.append(str(delta.get("text") or ""))
        if delta.get("type") == "input_json_delta" and tools:
            tools[-1]["partial_json"] = tools[-1].get("partial_json", "") + str(
                delta.get("partial_json") or "")
    return {"text": "".join(text), "tools": tools, "event_names": event_names,
            "usage": usage, "stop_reason": stop_reason}


class Runner:
    def __init__(self, base_url: str, out: Path, timeout: float) -> None:
        self.base_url, self.out, self.timeout = base_url, out, timeout

    def call(self, name: str, path: str, *, request_bytes: bytes | None = None,
             body: dict[str, Any] | None = None, stream: bool = False,
             base_url: str | None = None) -> dict[str, Any]:
        if request_bytes is None:
            if body is None:
                raise ValueError("request body is required")
            request_bytes = json_bytes(body)
        case = self.out / "raw" / name
        case.mkdir(parents=True, exist_ok=True)
        (case / "request.body").write_bytes(request_bytes)
        started = time.monotonic()
        status: int | None = None
        raw = b""
        error: str | None = None
        try:
            request = urllib.request.Request(endpoint(base_url or self.base_url, path),
                                              data=request_bytes,
                                              headers={"Content-Type": "application/json"}, method="POST")
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                status, raw = response.status, response.read()
        except urllib.error.HTTPError as exc:
            status, raw, error = exc.code, exc.read(), f"HTTP {exc.code}"
        except Exception as exc:
            error = f"{type(exc).__name__}: {exc}"
        (case / "response.body").write_bytes(raw)
        parsed: Any = None
        parse_error: str | None = None
        events: list[dict[str, Any]] = []
        if raw:
            if stream:
                events = parse_sse(raw)
            else:
                try:
                    parsed = json.loads(raw)
                except json.JSONDecodeError as exc:
                    parse_error = str(exc)
        meta = {"name": name, "path": path, "url": safe_url(endpoint(base_url or self.base_url, path)),
                "stream": stream, "status": status,
                "elapsed_ms": round((time.monotonic() - started) * 1000, 3),
                "request_bytes": len(request_bytes), "request_sha256": sha256(request_bytes),
                "response_bytes": len(raw), "response_sha256": sha256(raw), "error": error,
                "parse_error": parse_error, "sse_events": len(events) if stream else None}
        write_json(case / "receipt.json", meta)
        return {"meta": meta, "json": parsed, "events": events}


def protocol_json(result: dict[str, Any], *, status: int = 200) -> bool:
    return result["meta"]["status"] == status and isinstance(result.get("json"), dict)


def protocol_openai_stream(result: dict[str, Any]) -> bool:
    if result["meta"]["status"] != 200:
        return False
    events = result["events"]
    if not events or any(e.get("data_error") for e in events):
        return False
    has_finish = any(choice.get("finish_reason") is not None
                     for event in events if isinstance(event.get("data"), dict)
                     for choice in event["data"].get("choices") or []
                     if isinstance(choice, dict))
    return any(e.get("data") for e in events) and has_finish and any(
        e.get("data_text") == "[DONE]" for e in events)


def protocol_anthropic_stream(result: dict[str, Any]) -> bool:
    if result["meta"]["status"] != 200:
        return False
    if any(e.get("data_error") for e in result["events"]):
        return False
    names = [e.get("event") for e in result["events"]]
    return bool(names) and names[0] == "message_start" and names[-1] == "message_stop"


def protocol_anthropic_message(result: dict[str, Any]) -> bool:
    if not protocol_json(result):
        return False
    obj = result["json"]
    return (obj.get("type") == "message" and obj.get("role") == "assistant" and
            isinstance(obj.get("content"), list))


def openai_tool_arguments(tool: dict[str, Any]) -> dict[str, Any] | None:
    try:
        arguments = tool.get("function", {}).get("arguments")
        if isinstance(arguments, str):
            arguments = json.loads(arguments)
        if not isinstance(arguments, dict):
            return None
        return arguments
    except (TypeError, json.JSONDecodeError):
        return None


def openai_tool_control_ok(tools: Any) -> bool:
    if not isinstance(tools, list) or len(tools) != 1 or not isinstance(tools[0], dict):
        return False
    tool = tools[0]
    function = tool.get("function")
    return (isinstance(function, dict) and function.get("name") == "get_weather" and
            openai_tool_arguments(tool) == EXPECTED_TOOL_ARGS)


def anthropic_tool_control_ok(tools: Any) -> bool:
    if not isinstance(tools, list) or len(tools) != 1 or not isinstance(tools[0], dict):
        return False
    tool = tools[0]
    arguments: Any = tool.get("input")
    if "partial_json" in tool:
        try:
            arguments = json.loads(str(tool["partial_json"]))
        except (TypeError, json.JSONDecodeError):
            return False
    return tool.get("name") == "get_weather" and arguments == EXPECTED_TOOL_ARGS


def build_literal_bodies(model: str) -> dict[str, tuple[str, dict[str, Any], bool]]:
    literal = ("Answer in one short sentence. Repeat this exact text as prose: "
               "The literal marker is `<tool_call>` and the literal closing marker is "
               "`</tool_call>`. Neither marker requests a tool call.")
    openai_tool = {"type": "function", "function": {"name": "get_weather",
                    "description": "Get the weather for a city.", "parameters": {
                        "type": "object", "properties": {"city": {"type": "string"}},
                        "required": ["city"], "additionalProperties": False}}}
    anthropic_tool = {"name": "get_weather", "description": "Get the weather for a city.",
                      "input_schema": {"type": "object", "properties": {"city": {"type": "string"}},
                                        "required": ["city"], "additionalProperties": False}}
    out: dict[str, tuple[str, dict[str, Any], bool]] = {}
    for surface in ("openai", "anthropic"):
        for streaming in (False, True):
            suffix = "stream" if streaming else "blocking"
            body: dict[str, Any] = {"model": model,
                "messages": [{"role": "user", "content": literal}],
                "temperature": 0, "max_tokens": 1024}
            if surface == "openai":
                body["chat_template_kwargs"] = {"reasoning_effort": "low"}
            if streaming:
                body["stream"] = True
            path = "/v1/chat/completions" if surface == "openai" else "/v1/messages"
            out[f"xml-{surface}-{suffix}"] = (path, body, streaming)
            if surface == "openai":
                control: dict[str, Any] = {"model": model,
                    "messages": [{"role": "user", "content": "Call get_weather for Paris."}],
                    "tools": [openai_tool],
                    "tool_choice": {"type": "function", "function": {"name": "get_weather"}},
                    "temperature": 0, "max_tokens": 1024,
                    "chat_template_kwargs": {"reasoning_effort": "low"}}
            else:
                control = {"model": model,
                    "messages": [{"role": "user", "content": "Call get_weather for Paris."}],
                    "tools": [anthropic_tool], "tool_choice": {"type": "tool", "name": "get_weather"},
                    "temperature": 0, "max_tokens": 1024}
            if streaming:
                control["stream"] = True
            out[f"tool-{surface}-{suffix}"] = (path, control, streaming)
    return out


def prepare_fixtures(evidence: Path, out: Path, *, include_long: bool, model: str) -> dict[str, Any]:
    quality = evidence / "raw" / "quality"
    on_http, remaining_http = quality / "on" / "http", quality / "remaining" / "http"
    reference, fixtures = evidence / "raw" / "reference", out / "fixtures"
    manifest: dict[str, Any] = {}
    nll_source = remaining_http / "0006-canonical-nll" / "request.body"
    nll_info = copy_fixture(nll_source, fixtures / "canonical-nll.request.json", evidence)
    nll = read_json(nll_source)
    ids = nll.get("prompt")
    if not isinstance(ids, list):
        raise ValueError("canonical NLL fixture has no prompt ID array")
    if len(ids) != 27034 or compact_sha(ids) != "a28f25b5d5564bbe42fd47799788317bbb7bfb586e133c2d9ab7af7ad947203c":
        raise ValueError("canonical NLL IDs do not match the preserved 27,034-ID fixture")
    manifest["canonical_nll"] = {**nll_info, "ids": len(ids), "ids_compact_sha256": compact_sha(ids),
        "reference_observed_a4": copy_fixture(reference / "observed-a4.json", fixtures / "observed-a4.json", evidence),
        "reference_earlier_shared_a4": copy_fixture(reference / "earlier-shared-a4.json", fixtures / "earlier-shared-a4.json", evidence)}
    # The preserved recorder includes one empty failed-attempt folder. The
    # prefix arm also includes its one-token warmup, so select JSON request
    # bodies and separate that warmup before copying measured prompts.
    plain_sources = []
    for source in sorted(on_http.glob("*-greedy-c1/request.body")):
        if not source.stat().st_size:
            continue
        try:
            read_json(source)
        except json.JSONDecodeError:
            continue
        plain_sources.append(source)
    prefix_all = []
    for source in sorted(on_http.glob("*-greedy-c1p/request.body")):
        if not source.stat().st_size:
            continue
        try:
            body = read_json(source)
        except json.JSONDecodeError:
            continue
        prefix_all.append((source, body))
    warmup_sources = [source for source, body in prefix_all if body.get("max_tokens") == 1]
    prefix_sources = [source for source, body in prefix_all if body.get("max_tokens") != 1]
    if len(plain_sources) != 8 or len(prefix_sources) != 8 or len(warmup_sources) != 1:
        raise ValueError("preserved greedy fixture set must contain 8 plain and 8 prefix bodies")
    manifest["greedy_plain"] = [copy_fixture(src, fixtures / "greedy" / f"plain-{i:02d}.json", evidence)
                                 for i, src in enumerate(plain_sources, 1)]
    manifest["greedy_prefix"] = [copy_fixture(src, fixtures / "greedy" / f"prefix-{i:02d}.json", evidence)
                                  for i, src in enumerate(prefix_sources, 1)]
    manifest["greedy_prefix_warmup"] = copy_fixture(warmup_sources[0], fixtures / "greedy" / "prefix-warmup.json", evidence)
    manifest["schema_union"] = copy_fixture(on_http / "0077-schema-union" / "request.body",
                                              fixtures / "schema-union.request.json", evidence)
    manifest["schema_none_control"] = copy_fixture(remaining_http / "0005-schema-union-tool-choice-none-control" / "request.body",
                                                     fixtures / "schema-none-control.request.json", evidence)
    if include_long:
        needle_sources = sorted(remaining_http.glob("*-needle/request.body"))
        expected_source = quality / "remaining" / "needle-final-low.jsonl"
        expected_rows = [json.loads(line) for line in expected_source.read_text().splitlines() if line.strip()]
        if len(needle_sources) != 60 or len(expected_rows) != 60:
            raise ValueError("preserved seeded long-context fixtures must contain 60 bodies and 60 rows")
        expected_by_answer: dict[str, dict[str, Any]] = {}
        for expected in expected_rows:
            answer = expected.get("answer")
            if not isinstance(answer, str) or not EIGHT_DIGITS_RE.fullmatch(answer):
                raise ValueError(f"invalid seeded expected answer: {answer!r}")
            if answer in expected_by_answer:
                raise ValueError(f"duplicate seeded expected answer: {answer}")
            expected_by_answer[answer] = expected
        rows: list[dict[str, Any]] = []
        for i, src in enumerate(needle_sources, 1):
            ground_truth = needle_ground_truth(read_json(src))
            expected = expected_by_answer.get(ground_truth["answer"])
            if expected is None:
                raise ValueError(
                    f"no preserved expected metadata for derived answer {ground_truth['answer']} "
                    f"from {src}"
                )
            copied = copy_fixture(src, fixtures / "long" / f"needle-{i:02d}.json", evidence)
            rows.append({"fixture": copied, "expected": expected,
                         "ground_truth": ground_truth,
                         "expected_match": "derived_answer"})
        if {item["ground_truth"]["answer"] for item in rows} != set(expected_by_answer):
            raise ValueError("derived seeded answers do not cover the expected metadata exactly")
        manifest["long_context"] = {"requests": rows, "expected_source": rel_source(expected_source, evidence),
            "seed": 20261018, "concurrency": 4, "reasoning_effort": "low", "max_tokens": 2048,
            "ground_truth": {"method": "parse_request_tables_by_query",
                             "mapping_key": "answer",
                             "arrival_order_used": False}}
    literal_dir = fixtures / "literal"
    literal_dir.mkdir(parents=True, exist_ok=True)
    literal_manifest: dict[str, Any] = {}
    for name, (path, body, streaming) in build_literal_bodies(model).items():
        target = literal_dir / f"{name}.json"
        target.write_bytes(json_bytes(body))
        literal_manifest[name] = {"path": str(target), "bytes": target.stat().st_size,
            "sha256": sha256(target.read_bytes()), "endpoint": path, "stream": streaming}
    manifest["literal_xml_and_tools"] = literal_manifest
    return manifest


def load_fixture(manifest: dict[str, Any], key: str) -> Path:
    return Path(manifest[key]["path"])


def nll_summary(result: dict[str, Any], request: dict[str, Any], manifest: dict[str, Any]) -> dict[str, Any]:
    row: dict[str, Any] = {"status": result["meta"]["status"], "protocol_ok": protocol_json(result),
                           "semantic_ok": None, "engine_signal": None}
    if not row["protocol_ok"]:
        row["engine_signal"] = "canonical_nll_http_or_json_failure"
        return row
    try:
        lp = result["json"]["choices"][0]["logprobs"]["token_logprobs"]
        ids, n = request["prompt"], len(request["prompt"])
        if len(lp) < n or any(x is None or not math.isfinite(float(x)) for x in lp[1:n]):
            raise ValueError("missing/nonfinite prompt scores")
        value = -sum(float(x) for x in lp[1:n]) / (n - 1)
        refs: dict[str, Any] = {}
        for label in ("reference_observed_a4", "reference_earlier_shared_a4"):
            ref = read_json(Path(manifest["canonical_nll"][label]["path"]))
            ref_nll = -sum(float(x) for x in ref["lp"][1:n]) / (n - 1)
            refs[label] = {"nll": ref_nll, "delta": value - ref_nll}
        row.update({"nll_nats_per_token": value, "score_positions": [1, n - 1], "references": refs})
    except (KeyError, IndexError, TypeError, ValueError) as exc:
        row["protocol_ok"], row["engine_signal"] = False, f"invalid_canonical_logprobs: {exc}"
    return row


def run_greedy(runner: Runner, manifest: dict[str, Any], serial_url: str | None) -> dict[str, Any]:
    plain = [Path(item["path"]) for item in manifest["greedy_plain"]]
    prefix = [Path(item["path"]) for item in manifest["greedy_prefix"]]
    arms = {"c1": (plain, 1, False), "c4": (plain, 4, False), "c8": (plain, 8, False),
            "c1p": (prefix, 1, True), "c4p": (prefix, 4, True)}
    outputs: dict[str, list[dict[str, Any]]] = {}

    def one(arm: str, index: int, fixture: Path, base_url: str | None = None,
            serial_control: str | None = None) -> dict[str, Any]:
        exact_bytes = fixture.read_bytes()
        request_bytes = exact_bytes
        mutation: dict[str, Any] | None = None
        if serial_control == "same_server_disable_mtp":
            original_body = json.loads(exact_bytes)
            body = dict(original_body)
            before_present = "disable_mtp" in body
            before = body.get("disable_mtp")
            body["disable_mtp"] = True
            request_bytes = json_bytes(body)
            changed_keys = sorted(key for key in set(body) | set(original_body)
                                  if body.get(key) != original_body.get(key))
            mutation = {"control": serial_control, "field": "disable_mtp",
                        "before_present": before_present, "before": before, "after": True,
                        "mutated": before != True, "changed_keys": changed_keys,
                        "only_mutation": changed_keys == ["disable_mtp"],
                        "exact_request_sha256": sha256(exact_bytes),
                        "sent_request_sha256": sha256(request_bytes)}
        elif serial_control == "separate_serial_url":
            mutation = {"control": serial_control, "field": "disable_mtp", "mutated": False,
                        "only_mutation": False, "exact_request_sha256": sha256(exact_bytes),
                        "sent_request_sha256": sha256(request_bytes)}
        case_name = f"greedy/{serial_control and 'serial-' or ''}{arm}-{index:02d}"
        result = runner.call(case_name, "/v1/chat/completions",
                             request_bytes=request_bytes, base_url=base_url)
        if serial_control:
            case = runner.out / "raw" / case_name
            (case / "request.exact.body").write_bytes(exact_bytes)
            write_json(case / "request.mutation.json", mutation or {})
        row: dict[str, Any] = {"index": index, "fixture": str(fixture), "status": result["meta"]["status"],
                               "protocol_ok": False, "semantic_ok": None, "engine_signal": None}
        if serial_control:
            row["serial_control"] = serial_control
            row["request_mutation"] = mutation
        try:
            view = response_view(result["json"])
            row["protocol_ok"] = result["meta"]["status"] == 200 and valid_openai_view(view)
            row["view"] = view
            row["text_sha256"] = sha256(text_from_openai(view).encode())
            row["cached_tokens"] = (result["json"].get("usage") or {}).get("prompt_tokens_details", {}).get("cached_tokens")
            row["budget_truncated"] = view.get("finish_reason") == "length"
            if not row["protocol_ok"]:
                row["engine_signal"] = "incomplete_openai_envelope"
        except (TypeError, KeyError, IndexError, ValueError) as exc:
            row["engine_signal"] = f"invalid_greedy_envelope: {exc}"
        return row

    for arm, (fixtures, concurrency, has_prefix) in arms.items():
        if has_prefix:
            warmup = Path(manifest["greedy_prefix_warmup"]["path"])
            runner.call(f"greedy/{arm}-prefix-warmup", "/v1/chat/completions", request_bytes=warmup.read_bytes())
        if concurrency == 1:
            rows = [one(arm, i, fixture) for i, fixture in enumerate(fixtures, 1)]
        else:
            with concurrent.futures.ThreadPoolExecutor(max_workers=concurrency) as pool:
                rows = list(pool.map(lambda pair: one(arm, pair[0], pair[1]), enumerate(fixtures, 1)))
        outputs[arm] = rows

    comparisons = [compare_row_pairs("c1", "c4", outputs["c1"], outputs["c4"]),
                   compare_row_pairs("c1", "c8", outputs["c1"], outputs["c8"]),
                   compare_row_pairs("c1p", "c4p", outputs["c1p"], outputs["c4p"])]
    serial_control = "separate_serial_url" if serial_url else "same_server_disable_mtp"
    serial_rows = [one("c1", i, fixture, serial_url, serial_control)
                   for i, fixture in enumerate(plain, 1)]
    outputs["serial"] = serial_rows
    serial_comparison = compare_row_pairs("c1", "serial", outputs["c1"], serial_rows)
    serial = {"available": True, "control": serial_control, **serial_comparison,
              "rows": [{key: value for key, value in row.items() if key != "view"}
                       for row in serial_rows]}
    public_outputs = {
        arm: [{key: value for key, value in row.items() if key != "view"} for row in rows]
        for arm, rows in outputs.items()
    }
    return {"arms": public_outputs, "comparisons": comparisons, "serial_vs_mtp": serial,
            "prefix_cache_signal": {arm: {"all_cached_positive": all((row.get("cached_tokens") or 0) > 0 for row in outputs[arm]),
                                           "cached_tokens": [row.get("cached_tokens") for row in outputs[arm]]}
                                    for arm in ("c1p", "c4p")}}


def schema_summary(runner: Runner, manifest: dict[str, Any]) -> dict[str, Any]:
    cases = {"union": load_fixture(manifest, "schema_union"),
             "tool_choice_none": load_fixture(manifest, "schema_none_control")}
    rows: dict[str, Any] = {}
    for name, fixture in cases.items():
        result = runner.call(f"schema/{name}", "/v1/chat/completions", request_bytes=fixture.read_bytes())
        row: dict[str, Any] = {"status": result["meta"]["status"], "protocol_ok": False,
                               "semantic_ok": None, "semantic_category": None, "engine_signal": None}
        if protocol_json(result):
            try:
                view = response_view(result["json"])
                row["protocol_ok"] = valid_openai_view(view)
                row["budget_truncated"] = view.get("finish_reason") == "length"
                if not row["protocol_ok"]:
                    row["engine_signal"] = "incomplete_schema_envelope"
                    rows[name] = row
                    continue
                row["tool_calls"] = view.get("tool_calls")
                if view.get("tool_calls"):
                    row["semantic_ok"], row["semantic_category"] = False, "model_tool_choice"
                else:
                    obj = json.loads(view.get("content") or "")
                    row["semantic_ok"] = obj == {"city": "Oslo", "temperature_c": 7}
                    row["semantic_category"] = "expected_json" if row["semantic_ok"] else "model_json_content"
            except (TypeError, KeyError, IndexError, ValueError, json.JSONDecodeError) as exc:
                row["protocol_ok"], row["engine_signal"] = False, f"invalid_schema_envelope: {exc}"
        else:
            row["engine_signal"] = "schema_http_or_json_failure"
        rows[name] = row
    return rows


def long_summary(runner: Runner, manifest: dict[str, Any]) -> dict[str, Any]:
    def one(pair: tuple[int, dict[str, Any]]) -> dict[str, Any]:
        index, item = pair
        result = runner.call(f"long/needle-{index:02d}", "/v1/chat/completions",
                             request_bytes=Path(item["fixture"]["path"]).read_bytes())
        ground_truth = item["ground_truth"]
        expected = str(ground_truth["answer"])
        row: dict[str, Any] = {"index": index, "rows": item["expected"].get("rows"),
                               "depth": item["expected"].get("depth"), "status": result["meta"]["status"],
                               "query_key": ground_truth["key"],
                               "table_a_code": ground_truth["code"],
                               "answer": expected,
                               "expected_metadata_answer": item["expected"].get("answer"),
                               "expected_metadata_out": item["expected"].get("out"),
                               "expected_match": item.get("expected_match"),
                               "request_content_chars": ground_truth["content_chars"],
                               "protocol_ok": False, "semantic_ok": None,
                               "semantic_category": None, "engine_signal": None}
        if protocol_json(result):
            try:
                view = response_view(result["json"])
                output = text_from_openai(view)
                content = view.get("content")
                row.update({"protocol_ok": valid_openai_view(view),
                            "output_tail": output[-60:],
                            "budget_truncated": view.get("finish_reason") == "length"})
                if row["protocol_ok"]:
                    semantic_ok = answer_in_content(content, expected)
                    row.update({"semantic_ok": semantic_ok,
                                "semantic_category": "retrieval_answer" if semantic_ok else "model_retrieval"})
                else:
                    row["engine_signal"] = "incomplete_long_envelope"
            except (TypeError, KeyError, IndexError, ValueError) as exc:
                row["engine_signal"] = f"invalid_long_envelope: {exc}"
        else:
            row["engine_signal"] = "long_http_or_json_failure"
        return row

    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
        result_rows = list(pool.map(one, enumerate(manifest["long_context"]["requests"], 1)))
    semantic = [row for row in result_rows if row.get("protocol_ok")]
    return {"seed": manifest["long_context"]["seed"], "concurrency": 4, "rows": result_rows,
            "protocol_ok": all(row.get("protocol_ok") for row in result_rows),
            "semantic_correct": sum(bool(row.get("semantic_ok")) for row in semantic),
            "semantic_total": len(semantic), "semantic_failures_are_model_observations": True}


def literal_summary(runner: Runner, model: str) -> dict[str, Any]:
    rows: dict[str, Any] = {}
    for name, (path, body, streaming) in build_literal_bodies(model).items():
        result = runner.call(f"literal/{name}", path, body=body, stream=streaming)
        row: dict[str, Any] = {"status": result["meta"]["status"], "protocol_ok": False,
                               "semantic_ok": None, "semantic_category": None,
                               "engine_signal": None, "budget_truncated": False}
        is_tool, surface = name.startswith("tool-"), name.split("-")[1]
        try:
            if streaming:
                if surface == "openai":
                    row["protocol_ok"] = protocol_openai_stream(result)
                    view = openai_stream_view(result["events"])
                    row["text"], row["tool_calls"] = text_from_openai(view), view.get("tool_calls")
                    row["budget_truncated"] = view.get("finish_reason") == "length"
                    if not row["protocol_ok"]:
                        row["engine_signal"] = "openai_stream_protocol_failure"
                    elif row["budget_truncated"]:
                        row["semantic_category"] = "inconclusive_budget"
                    elif is_tool:
                        row["semantic_ok"] = openai_tool_control_ok(view.get("tool_calls"))
                        row["semantic_category"] = "forced_tool" if row["semantic_ok"] else "model_tool_choice"
                    else:
                        marker = "<tool_call>" in row["text"] and "</tool_call>" in row["text"]
                        row["semantic_ok"], row["semantic_category"] = marker, "literal_prose" if marker else "model_literal_prose"
                        if view.get("tool_calls"):
                            row["engine_signal"] = "literal_marker_emitted_as_tool_call"
                else:
                    row["protocol_ok"] = protocol_anthropic_stream(result)
                    view = anthropic_stream_view(result["events"])
                    row["text"], row["tool_calls"] = view["text"], view["tools"]
                    row["budget_truncated"] = view.get("stop_reason") == "max_tokens"
                    if not row["protocol_ok"]:
                        row["engine_signal"] = "anthropic_stream_protocol_failure"
                    elif row["budget_truncated"]:
                        row["semantic_category"] = "inconclusive_budget"
                    elif is_tool:
                        row["semantic_ok"] = anthropic_tool_control_ok(view["tools"])
                        row["semantic_category"] = "forced_tool" if row["semantic_ok"] else "model_tool_choice"
                    else:
                        marker = "<tool_call>" in view["text"] and "</tool_call>" in view["text"]
                        row["semantic_ok"], row["semantic_category"] = marker, "literal_prose" if marker else "model_literal_prose"
                        if view["tools"]:
                            row["engine_signal"] = "literal_marker_emitted_as_tool_use"
            elif surface == "openai":
                view = response_view(result["json"])
                row["text"], row["tool_calls"] = text_from_openai(view), view.get("tool_calls")
                row["protocol_ok"] = result["meta"]["status"] == 200 and valid_openai_view(view)
                row["budget_truncated"] = view.get("finish_reason") == "length"
                if not row["protocol_ok"]:
                    row["engine_signal"] = "openai_blocking_protocol_failure"
                elif row["budget_truncated"]:
                    row["semantic_category"] = "inconclusive_budget"
                elif is_tool:
                    row["semantic_ok"] = openai_tool_control_ok(view.get("tool_calls"))
                    row["semantic_category"] = "forced_tool" if row["semantic_ok"] else "model_tool_choice"
                else:
                    marker = "<tool_call>" in row["text"] and "</tool_call>" in row["text"]
                    row["semantic_ok"], row["semantic_category"] = marker, "literal_prose" if marker else "model_literal_prose"
                    if view.get("tool_calls"):
                        row["engine_signal"] = "literal_marker_emitted_as_tool_call"
            else:
                obj = result["json"]
                row["protocol_ok"] = protocol_anthropic_message(result)
                row["text"], row["tool_calls"] = anthropic_text(obj), anthropic_tools(obj)
                row["budget_truncated"] = obj.get("stop_reason") == "max_tokens"
                if not row["protocol_ok"]:
                    row["engine_signal"] = "anthropic_blocking_protocol_failure"
                elif row["budget_truncated"]:
                    row["semantic_category"] = "inconclusive_budget"
                elif is_tool:
                    row["semantic_ok"] = anthropic_tool_control_ok(row["tool_calls"])
                    row["semantic_category"] = "forced_tool" if row["semantic_ok"] else "model_tool_choice"
                else:
                    marker = "<tool_call>" in row["text"] and "</tool_call>" in row["text"]
                    row["semantic_ok"], row["semantic_category"] = marker, "literal_prose" if marker else "model_literal_prose"
                    if row["tool_calls"]:
                        row["engine_signal"] = "literal_marker_emitted_as_tool_use"
        except (TypeError, KeyError, IndexError, ValueError) as exc:
            row["engine_signal"] = f"invalid_literal_envelope: {exc}"
        row["text_sha256"] = sha256(str(row.pop("text", "") or "").encode())
        rows[name] = row
    return rows


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", default=DEFAULT_URL, help="running server base URL")
    parser.add_argument("--serial-url", help="separately configured serial-control server URL")
    parser.add_argument("--out", default="qualification-output", type=Path)
    parser.add_argument("--mode", choices=MODES, default="baseline")
    parser.add_argument("--model", default=os.environ.get("SQ_MODEL", DEFAULT_MODEL))
    parser.add_argument("--evidence-root", default=DEFAULT_EVIDENCE, type=Path)
    parser.add_argument("--long", action="store_true", help="run the preserved 60-request seeded long-context set")
    parser.add_argument("--offline", action="store_true", help="copy and validate fixtures without contacting a server")
    parser.add_argument("--timeout", type=float, default=1800.0)
    args = parser.parse_args()
    evidence, out = args.evidence_root.resolve(), args.out.expanduser().resolve()
    if out.exists():
        raise SystemExit(f"output already exists; choose a new --out: {out}")
    out.mkdir(parents=True)
    manifest = prepare_fixtures(evidence, out, include_long=args.long, model=args.model)
    write_json(out / "fixtures-manifest.json", manifest)
    summary: dict[str, Any] = {"driver": str(Path(__file__).resolve()), "mode": args.mode, "url": safe_url(args.url),
        "serial_url_configured": bool(args.serial_url), "model": args.model, "evidence_root": str(evidence),
        "offline": args.offline, "long_requested": args.long,
        "fixture_manifest": str(out / "fixtures-manifest.json"), "results": {},
        "semantic_observations_are_not_engine_failures": True}
    if not args.offline:
        runner = Runner(args.url, out, args.timeout)
        nll_fixture = load_fixture(manifest, "canonical_nll")
        nll_result = runner.call("nll/canonical", "/v1/completions", request_bytes=nll_fixture.read_bytes())
        summary["results"]["canonical_nll"] = nll_summary(nll_result, read_json(nll_fixture), manifest)
        summary["results"]["greedy"] = run_greedy(runner, manifest, args.serial_url)
        summary["results"]["schema"] = schema_summary(runner, manifest)
        summary["results"]["literal_xml_and_tools"] = literal_summary(runner, args.model)
        if args.long:
            summary["results"]["long_context"] = long_summary(runner, manifest)
    else:
        summary["results"]["offline"] = {"fixture_count": sum(1 for item in (out / "fixtures").rglob("*") if item.is_file()),
                                           "network_calls": 0}
    write_json(out / "summary.json", summary)
    print(json.dumps(summary, indent=2, sort_keys=True, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
