#!/usr/bin/env python3
# SPDX-License-Identifier: AGPL-3.0-only

"""Shared short-video qualification for SparkQwen and SparkGLM.

This is deliberately an HTTP harness rather than a model-specific client. It
records the exact JSON request bytes, exact response bytes, fixture hashes, and
semantic checks for the temporal contracts that the engine must preserve.

The three short MP4s in ``fixtures/`` come from ``video_fixtures.py``. The
optional still and procedure fixtures are generated only with
``--generate-fixtures`` using Pillow and ffmpeg; no external or private media
is accepted by this harness.
"""

from __future__ import annotations

import argparse
import base64
import concurrent.futures
import datetime as dt
import hashlib
import json
import mimetypes
import os
from pathlib import Path
import subprocess
import sys
import time
from typing import Any, Callable
import urllib.error
import urllib.request


ROOT = Path(__file__).resolve().parent
FIXTURES = ROOT / "fixtures"
MODEL = os.environ.get("ATLAS_TEST_MODEL", "qwen3.8-flash-next-atlas")
SCHEMA = 1
SCENE_ORDER = ["red", "green", "blue"]
SCENE_LONGEST = {"order": "tie", "reverse": "tie", "duration": "green"}
SCENE_STARTS = {
    "order": {"red": 0.0, "green": 3.0, "blue": 6.0},
    "reverse": {"blue": 0.0, "green": 3.0, "red": 6.0},
    "duration": {"red": 0.0, "green": 2.0, "blue": 8.0},
}
PROCEDURE_ORDER = ["open", "pour", "mix", "bake", "serve"]
PROCEDURE_STARTS = {"open": 0.0, "pour": 5.0, "mix": 11.0, "bake": 18.0, "serve": 26.0}
CAP_PROCEDURE_ORDER = ["load", "prepare", "operate", "inspect", "finish"]
CAP_PROCEDURE_STARTS = {
    "load": 0.0,
    "prepare": 16.0,
    "operate": 32.0,
    "inspect": 48.0,
    "finish": 62.0,
}


class HarnessError(RuntimeError):
    """A local harness or fixture error, distinct from an HTTP failure."""


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def iso_now() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat().replace("+00:00", "Z")


def load_manifest() -> list[dict[str, Any]]:
    path = FIXTURES / "manifest.json"
    if not path.exists():
        raise HarnessError(f"missing fixture manifest: {path}")
    value = json.loads(path.read_text())
    if not isinstance(value, list):
        raise HarnessError("fixture manifest must be a JSON array")
    return value


def write_manifest(entries: list[dict[str, Any]]) -> None:
    (FIXTURES / "manifest.json").write_text(json.dumps(entries, indent=2) + "\n")


def find_fixture(name: str, manifest: list[dict[str, Any]]) -> dict[str, Any]:
    for entry in manifest:
        if entry.get("name") == name:
            path = FIXTURES / str(entry["file"])
            if not path.exists():
                raise HarnessError(f"manifest entry {name!r} points to missing {path}")
            actual = sha256_file(path)
            if actual != entry.get("sha256"):
                raise HarnessError(
                    f"fixture {name!r} SHA mismatch: manifest {entry.get('sha256')} != {actual}"
                )
            return {**entry, "path": str(path), "bytes": path.stat().st_size}
    raise HarnessError(f"fixture {name!r} is not in the manifest")


def fixture_receipt(entry: dict[str, Any]) -> dict[str, Any]:
    path = Path(str(entry["path"]))
    mime = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
    return {
        "name": entry["name"],
        "file": path.relative_to(ROOT).as_posix(),
        "mime": mime,
        "bytes": entry["bytes"],
        "sha256": entry["sha256"],
        "manifest": {k: v for k, v in entry.items() if k not in {"path", "bytes"}},
    }


def data_url(entry: dict[str, Any]) -> str:
    path = Path(str(entry["path"]))
    mime = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
    encoded = base64.b64encode(path.read_bytes()).decode("ascii")
    return f"data:{mime};base64,{encoded}"


def _font_for_fixture() -> Any:
    from PIL import ImageFont

    for candidate in (
        "/System/Library/Fonts/Supplemental/Arial.ttf",
        "/Library/Fonts/Arial.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    ):
        if Path(candidate).exists():
            return ImageFont.truetype(candidate, 42)
    return ImageFont.load_default()


def generate_auxiliary_fixtures() -> None:
    """Generate the deterministic still and longer sparse procedure clip."""

    try:
        from PIL import Image, ImageDraw
    except ImportError as exc:  # pragma: no cover - depends on operator host
        raise HarnessError("--generate-fixtures requires Pillow") from exc

    FIXTURES.mkdir(parents=True, exist_ok=True)
    font = _font_for_fixture()
    still = FIXTURES / "still_yellow.png"
    image = Image.new("RGB", (512, 384), "#d6ad16")
    draw = ImageDraw.Draw(image)
    draw.rectangle((8, 8, 503, 375), outline="white", width=8)
    draw.text((74, 170), "STILL YELLOW", fill="white", font=font)
    image.save(still, format="PNG", optimize=False)

    procedure = FIXTURES / "procedure_sparse.mp4"
    scenes = [("OPEN", 5), ("POUR", 6), ("MIX", 7), ("BAKE", 8), ("SERVE", 10)]
    fps = 2
    width, height = 640, 360
    colors = {
        "OPEN": (42, 80, 154),
        "POUR": (26, 126, 94),
        "MIX": (142, 77, 158),
        "BAKE": (184, 82, 36),
        "SERVE": (40, 132, 148),
    }
    raw = bytearray()
    frame_number = 0
    for label, seconds in scenes:
        for _ in range(seconds * fps):
            frame = Image.new("RGB", (width, height), colors[label])
            frame_draw = ImageDraw.Draw(frame)
            elapsed = frame_number / fps
            frame_draw.text((42, 52), f"STEP {label}", fill="white", font=font)
            frame_draw.text((42, 116), f"procedure time {elapsed:.1f}s", fill="white", font=font)
            # A moving bar makes sampling the procedure meaningful while the
            # large step label keeps the semantic gate easy to inspect.
            bar_x = 42 + int((width - 84 - 30) * ((frame_number % (fps * 10)) / (fps * 10)))
            frame_draw.rectangle((42, 260, width - 42, 290), outline="white", width=3)
            frame_draw.rectangle((bar_x, 264, min(bar_x + 30, width - 46), 286), fill="white")
            raw.extend(frame.tobytes())
            frame_number += 1
    command = [
        "ffmpeg",
        "-hide_banner",
        "-loglevel",
        "error",
        "-y",
        "-f",
        "rawvideo",
        "-pixel_format",
        "rgb24",
        "-video_size",
        f"{width}x{height}",
        "-framerate",
        str(fps),
        "-i",
        "pipe:0",
        "-an",
        "-c:v",
        "libx264",
        "-preset",
        "veryfast",
        "-crf",
        "20",
        "-pix_fmt",
        "yuv420p",
        "-movflags",
        "+faststart",
        str(procedure),
    ]
    try:
        subprocess.run(command, input=bytes(raw), check=True)
    except FileNotFoundError as exc:  # pragma: no cover - depends on host
        raise HarnessError("--generate-fixtures requires ffmpeg on PATH") from exc

    # This separate clip deliberately exceeds the engine's nominal 128-frame
    # video sample cap: it is 140 native frames (70 seconds at 2 fps).  The
    # scene labels are visible, but there is no clock or timestamp text, so a
    # passing temporal check must use the per-frame timestamp metadata.
    cap_procedure = FIXTURES / "procedure_cap.mp4"
    cap_scenes = [
        ("LOAD", 16),
        ("PREPARE", 16),
        ("OPERATE", 16),
        ("INSPECT", 14),
        ("FINISH", 8),
    ]
    cap_colors = {
        "LOAD": (34, 87, 148),
        "PREPARE": (32, 126, 92),
        "OPERATE": (135, 71, 152),
        "INSPECT": (176, 81, 35),
        "FINISH": (36, 125, 142),
    }
    cap_total_frames = sum(seconds for _, seconds in cap_scenes) * fps
    cap_raw = bytearray()
    cap_frame_number = 0
    for label, seconds in cap_scenes:
        for _ in range(seconds * fps):
            frame = Image.new("RGB", (width, height), cap_colors[label])
            frame_draw = ImageDraw.Draw(frame)
            frame_draw.text((42, 52), f"STEP {label}", fill="white", font=font)
            # A moving bar gives the decoder a visual temporal signal without
            # printing a timestamp that could make the task self-answering.
            progress = cap_frame_number / max(1, cap_total_frames - 1)
            bar_x = 42 + int((width - 84 - 30) * progress)
            frame_draw.rectangle((42, 260, width - 42, 290), outline="white", width=3)
            frame_draw.rectangle(
                (bar_x, 264, min(bar_x + 30, width - 46), 286), fill="white"
            )
            cap_raw.extend(frame.tobytes())
            cap_frame_number += 1
    cap_command = [
        "ffmpeg",
        "-hide_banner",
        "-loglevel",
        "error",
        "-y",
        "-f",
        "rawvideo",
        "-pixel_format",
        "rgb24",
        "-video_size",
        f"{width}x{height}",
        "-framerate",
        str(fps),
        "-i",
        "pipe:0",
        "-an",
        "-c:v",
        "libx264",
        "-preset",
        "veryfast",
        "-crf",
        "20",
        "-pix_fmt",
        "yuv420p",
        "-movflags",
        "+faststart",
        str(cap_procedure),
    ]
    try:
        subprocess.run(cap_command, input=bytes(cap_raw), check=True)
    except FileNotFoundError as exc:  # pragma: no cover - depends on host
        raise HarnessError("--generate-fixtures requires ffmpeg on PATH") from exc

    manifest = load_manifest()
    by_name = {str(item.get("name")): item for item in manifest}
    by_name["still_yellow"] = {
        "name": "still_yellow",
        "file": still.name,
        "sha256": sha256_file(still),
        "kind": "image",
        "description": "deterministic yellow still with a visible label",
    }
    by_name["procedure_sparse"] = {
        "name": "procedure_sparse",
        "file": procedure.name,
        "sha256": sha256_file(procedure),
        "kind": "video",
        "fps": fps,
        "duration": sum(seconds for _, seconds in scenes),
        "scenes": [[label.lower(), seconds] for label, seconds in scenes],
        "description": "36-second deterministic procedure clip at 2 fps",
    }
    by_name["procedure_cap"] = {
        "name": "procedure_cap",
        "file": cap_procedure.name,
        "sha256": sha256_file(cap_procedure),
        "kind": "video",
        "fps": fps,
        "duration": sum(seconds for _, seconds in cap_scenes),
        "native_frames": cap_total_frames,
        "scenes": [[label.lower(), seconds] for label, seconds in cap_scenes],
        "description": (
            "70-second, 140-frame procedure clip with no visible timestamps; "
            "tests the 128-frame sample cap"
        ),
    }
    # Keep the original three controls first, then the generated fixtures.
    ordered = [by_name[name] for name in ("order", "reverse", "duration")]
    ordered.extend(
        by_name[name]
        for name in ("still_yellow", "procedure_sparse", "procedure_cap")
    )
    write_manifest(ordered)


def video_part(entry: dict[str, Any]) -> dict[str, Any]:
    return {"type": "video_url", "video_url": {"url": data_url(entry)}}


def image_part(entry: dict[str, Any]) -> dict[str, Any]:
    return {"type": "image_url", "image_url": {"url": data_url(entry)}}


def text_part(text: str) -> dict[str, Any]:
    return {"type": "text", "text": text}


def request_body(case: str, messages: list[dict[str, Any]], *, n: int = 1) -> dict[str, Any]:
    body: dict[str, Any] = {
        "model": MODEL,
        "messages": messages,
        "temperature": 0,
        "top_p": 1,
        "max_tokens": 240,
        "chat_template_kwargs": {"enable_thinking": False},
        "cache_salt": f"qwen-video-qual-20261023-{case}",
    }
    if n != 1:
        body["n"] = n
    return body


def post_json(
    base_url: str,
    body: dict[str, Any],
    timeout_s: float,
    *,
    campaign_zero: float | None = None,
) -> dict[str, Any]:
    request_text = json.dumps(body, ensure_ascii=False, separators=(",", ":"))
    request_bytes = request_text.encode("utf-8")
    headers = {"Content-Type": "application/json"}
    api_key = os.environ.get("ATLAS_API_KEY")
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    request = urllib.request.Request(
        base_url.rstrip("/") + "/v1/chat/completions",
        data=request_bytes,
        headers=headers,
        method="POST",
    )
    started = time.monotonic()
    status: int | None = None
    response_bytes = b""
    error: str | None = None
    try:
        with urllib.request.urlopen(request, timeout=timeout_s) as response:
            status = response.status
            response_bytes = response.read()
    except urllib.error.HTTPError as exc:
        status = exc.code
        response_bytes = exc.read()
        error = f"HTTPError: {exc}"
    except Exception as exc:  # capture transport failures in the receipt
        error = f"{type(exc).__name__}: {exc}"
    ended = time.monotonic()
    response_text = response_bytes.decode("utf-8", "replace")
    try:
        response_json: Any = json.loads(response_text) if response_text else None
    except json.JSONDecodeError:
        response_json = None
    result = {
        "request": body,
        "request_json": request_text,
        "request_sha256": sha256_bytes(request_bytes),
        "authorization_present": bool(api_key),
        "response_status": status,
        "response_raw": response_text,
        "response_raw_base64": base64.b64encode(response_bytes).decode("ascii"),
        "response_sha256": sha256_bytes(response_bytes),
        "response": response_json,
        "elapsed_s": round(ended - started, 6),
        "started_offset_s": (
            round(started - campaign_zero, 6) if campaign_zero is not None else None
        ),
        "error": error,
    }
    return result


def choice_texts(response: Any) -> list[str]:
    if not isinstance(response, dict):
        return []
    texts: list[str] = []
    for choice in response.get("choices") or []:
        message = choice.get("message") if isinstance(choice, dict) else None
        if not isinstance(message, dict):
            continue
        content = message.get("content", "")
        if isinstance(content, str):
            texts.append(content)
        elif isinstance(content, list):
            texts.append(
                "".join(
                    str(part.get("text", ""))
                    for part in content
                    if isinstance(part, dict) and part.get("type") == "text"
                )
            )
    return texts


def parse_json_answer(text: str) -> tuple[dict[str, Any] | None, str | None]:
    start = text.find("{")
    end = text.rfind("}")
    if start < 0 or end <= start:
        return None, "response did not contain a JSON object"
    try:
        value = json.loads(text[start : end + 1])
    except json.JSONDecodeError as exc:
        return None, f"invalid JSON answer: {exc}"
    if not isinstance(value, dict):
        return None, "answer JSON was not an object"
    return value, None


def check_scene_answer(
    response: Any,
    *,
    expected_order: list[str],
    expected_longest: str,
    expected_starts: dict[str, float],
    tolerance_s: float = 1.5,
    choices_expected: int = 1,
) -> dict[str, Any]:
    texts = choice_texts(response)
    checks: dict[str, Any] = {"choices": len(texts), "passed": False}
    if len(texts) != choices_expected:
        checks["error"] = f"expected {choices_expected} choices, got {len(texts)}"
        return checks
    parsed: list[dict[str, Any]] = []
    errors: list[str] = []
    for index, text in enumerate(texts):
        value, error = parse_json_answer(text)
        if error:
            errors.append(f"choice {index}: {error}")
            continue
        assert value is not None
        parsed.append(value)
        order = [str(item).lower() for item in value.get("order", [])]
        if order != expected_order:
            errors.append(f"choice {index}: order {order!r} != {expected_order!r}")
        longest = str(value.get("longest", "")).lower()
        if expected_longest != "tie" and longest != expected_longest:
            errors.append(f"choice {index}: longest {longest!r} != {expected_longest!r}")
        starts = value.get("starts_seconds")
        # The prompts request timestamps but do not require a map. An ordered
        # list carries the same ground truth when its length matches order.
        if isinstance(starts, list) and len(starts) == len(order):
            starts = dict(zip(order, starts))
        if isinstance(starts, dict):
            starts = {str(key).lower(): val for key, val in starts.items()}
        if not isinstance(starts, dict):
            errors.append(f"choice {index}: starts_seconds is missing")
            continue
        for color, target in expected_starts.items():
            try:
                actual = float(starts[color])
            except (KeyError, TypeError, ValueError):
                errors.append(f"choice {index}: missing numeric start for {color}")
                continue
            if abs(actual - target) > tolerance_s:
                errors.append(
                    f"choice {index}: {color} start {actual:.2f}s outside {target:.2f}±{tolerance_s:.2f}s"
                )
    checks["parsed"] = parsed
    checks["errors"] = errors
    checks["passed"] = not errors
    return checks


def check_two_clip_answer(response: Any) -> dict[str, Any]:
    texts = choice_texts(response)
    checks: dict[str, Any] = {"choices": len(texts), "passed": False}
    if len(texts) != 1:
        checks["error"] = f"expected one choice, got {len(texts)}"
        return checks
    value, error = parse_json_answer(texts[0])
    if error:
        checks["error"] = error
        return checks
    assert value is not None
    first = [str(item).lower() for item in value.get("first_order", [])]
    second = [str(item).lower() for item in value.get("second_order", [])]
    checks.update({"parsed": value, "first_order": first, "second_order": second})
    checks["passed"] = first == SCENE_ORDER and second == ["blue", "green", "red"]
    if not checks["passed"]:
        checks["error"] = "two video orders did not remain distinct and ordered"
    return checks


def check_mixed_answer(response: Any) -> dict[str, Any]:
    texts = choice_texts(response)
    checks: dict[str, Any] = {"choices": len(texts), "passed": False}
    if len(texts) != 1:
        checks["error"] = f"expected one choice, got {len(texts)}"
        return checks
    value, error = parse_json_answer(texts[0])
    if error:
        checks["error"] = error
        return checks
    assert value is not None
    video = [str(item).lower() for item in value.get("video_order", [])]
    still = str(value.get("still_color", "")).lower()
    checks.update({"parsed": value, "video_order": video, "still_color": still})
    checks["passed"] = video == SCENE_ORDER and still == "yellow"
    if not checks["passed"]:
        checks["error"] = "mixed still/video answer did not preserve both modalities"
    return checks


def check_procedure_answer(response: Any) -> dict[str, Any]:
    checks = check_scene_answer(
        response,
        expected_order=PROCEDURE_ORDER,
        expected_longest="tie",
        expected_starts=PROCEDURE_STARTS,
        tolerance_s=2.0,
    )
    # Procedure uses the same ``order`` / ``starts_seconds`` schema but has no
    # meaningful longest scene; the model may omit it, so remove that check's
    # tie-specific failure only after the temporal checks have passed.
    if checks.get("parsed"):
        for value in checks["parsed"]:
            value.pop("longest", None)
        checks["passed"] = not any(
            "longest" in error for error in checks.get("errors", [])
        ) and not any(
            "order" in error or "start" in error for error in checks.get("errors", [])
        )
    return checks


def check_cap_procedure_answer(response: Any) -> dict[str, Any]:
    """Check the long clip whose final scene is past the nominal 64 s cap."""

    checks = check_scene_answer(
        response,
        expected_order=CAP_PROCEDURE_ORDER,
        expected_longest="tie",
        expected_starts=CAP_PROCEDURE_STARTS,
        tolerance_s=4.0,
    )
    if checks.get("parsed"):
        for value in checks["parsed"]:
            value.pop("longest", None)
        checks["passed"] = not any(
            "order" in error or "start" in error for error in checks.get("errors", [])
        )
    return checks


def run_single_case(
    case: str,
    body: dict[str, Any],
    checker: Callable[[Any], dict[str, Any]],
    base_url: str,
    timeout_s: float,
) -> dict[str, Any]:
    receipt = post_json(base_url, body, timeout_s)
    semantic = checker(receipt.get("response")) if receipt.get("response_status") == 200 else {
        "passed": False,
        "error": f"HTTP status {receipt.get('response_status')}",
    }
    receipt.update({"case": case, "semantic": semantic, "passed": bool(semantic.get("passed"))})
    return receipt


def build_cases(
    manifest: list[dict[str, Any]],
    *,
    include_procedure: bool,
) -> list[tuple[str, dict[str, Any], Callable[[Any], dict[str, Any]]]]:
    order = find_fixture("order", manifest)
    reverse = find_fixture("reverse", manifest)
    duration = find_fixture("duration", manifest)
    still = find_fixture("still_yellow", manifest)
    cases: list[tuple[str, dict[str, Any], Callable[[Any], dict[str, Any]]]] = []

    def scene_prompt() -> str:
        return (
            "Inspect the entire video, including its timing. Return exactly one JSON object "
            "with keys order (array of color names), longest (color name or tie), and "
            "starts_seconds (object with one decimal-second start time for each color). "
            "Use the clip start as zero and do not assume a uniform frame rate. No Markdown."
        )

    for name, entry in (("order", order), ("reverse", reverse), ("duration", duration)):
        body = request_body(
            name,
            [{"role": "user", "content": [video_part(entry), text_part(scene_prompt())]}],
        )
        expected_order = (
            SCENE_ORDER
            if name in {"order", "duration"}
            else ["blue", "green", "red"]
        )
        checker = lambda response, name=name, expected_order=expected_order: check_scene_answer(
            response,
            expected_order=expected_order,
            expected_longest=SCENE_LONGEST[name],
            expected_starts=SCENE_STARTS[name],
        )
        cases.append((name, body, checker))

    mixed_body = request_body(
        "mixed-still-video",
        [
            {
                "role": "user",
                "content": [
                    video_part(order),
                    image_part(still),
                    text_part(
                        'Return exactly JSON with keys video_order and still_color. '
                        'The video comes first and the still image comes second. No Markdown.'
                    ),
                ],
            }
        ],
    )
    cases.append(("mixed-still-video", mixed_body, check_mixed_answer))

    two_body = request_body(
        "two-clips-one-prompt",
        [
            {
                "role": "user",
                "content": [
                    video_part(order),
                    video_part(reverse),
                    text_part(
                        'For EACH video, list ALL its colors in chronological order from beginning '
                        'to end. Return JSON with first_order and second_order, each an array '
                        'of color-name strings. The first video is the first video content part; '
                        'the second video is the second content part. No Markdown.'
                    ),
                ],
            }
        ],
    )
    cases.append(("two-clips-one-prompt", two_body, check_two_clip_answer))

    history_body = request_body(
        "multiturn-repeated-video",
        [
            {
                "role": "user",
                "content": [
                    video_part(order),
                    text_part("Study this video. I will ask you about the same video again."),
                ],
            },
            {"role": "assistant", "content": "I studied the video and am ready."},
            {
                "role": "user",
                "content": [
                    video_part(order),
                    text_part(
                        'Return exactly JSON with keys order and starts_seconds for the '
                        'repeated video. No Markdown.'
                    ),
                ],
            },
        ],
    )
    cases.append(
        (
            "multiturn-repeated-video",
            history_body,
            lambda response: check_scene_answer(
                response,
                expected_order=SCENE_ORDER,
                expected_longest="tie",
                expected_starts=SCENE_STARTS["order"],
            ),
        )
    )

    n2_body = request_body(
        "n2-video",
        [
            {
                "role": "user",
                "content": [video_part(order), text_part(scene_prompt())],
            }
        ],
        n=2,
    )
    cases.append(
        (
            "n2-video",
            n2_body,
            lambda response: check_scene_answer(
                response,
                expected_order=SCENE_ORDER,
                expected_longest="tie",
                expected_starts=SCENE_STARTS["order"],
                choices_expected=2,
            ),
        )
    )

    if include_procedure:
        procedure = find_fixture("procedure_sparse", manifest)
        body = request_body(
            "procedure-sparse",
            [
                {
                    "role": "user",
                    "content": [
                        video_part(procedure),
                        text_part(
                            "Inspect this full procedure video. Return exactly JSON with "
                            "keys order and starts_seconds. The step names are open, pour, "
                            "mix, bake, serve. Use approximate seconds from the clip start. "
                            "No Markdown."
                        ),
                    ],
                }
            ],
        )
        cases.append(("procedure-sparse", body, check_procedure_answer))
        cap_procedure = find_fixture("procedure_cap", manifest)
        cap_body = request_body(
            "procedure-frame-cap",
            [
                {
                    "role": "user",
                    "content": [
                        video_part(cap_procedure),
                        text_part(
                            "Inspect this full 70-second procedure video. It has no visible "
                            "clock or timestamps. Use the temporal metadata supplied with "
                            "the video. Return exactly JSON with keys order and "
                            "starts_seconds. The step names are load, prepare, operate, "
                            "inspect, finish. Use approximate seconds from the clip start. "
                            "No Markdown."
                        ),
                    ],
                }
            ],
        )
        cases.append(("procedure-frame-cap", cap_body, check_cap_procedure_answer))
        if any(entry.get("name") == "procedure_hd" for entry in manifest):
            hd = find_fixture("procedure_hd", manifest)
            hd_body = json.loads(json.dumps(cap_body))
            hd_body["messages"][0]["content"][0] = video_part(hd)
            hd_body["cache_salt"] = "procedure-hd-frame-cap"
            cases.append(("procedure-hd-frame-cap", hd_body, check_cap_procedure_answer))
    return cases


def malformed_and_recovery(
    base_url: str,
    order: dict[str, Any],
    timeout_s: float,
) -> dict[str, Any]:
    invalid_url = "data:video/mp4;base64,not-a-valid-base64-video"
    invalid = request_body(
        "malformed-video",
        [
            {
                "role": "user",
                "content": [
                    {"type": "video_url", "video_url": {"url": invalid_url}},
                    text_part("Describe this video briefly."),
                ],
            }
        ],
    )
    invalid_receipt = post_json(base_url, invalid, timeout_s)
    recovery = request_body(
        "malformed-video-recovery",
        [
            {
                "role": "user",
                "content": [
                    video_part(order),
                    text_part(
                        "Inspect the full video and return exactly one JSON object with "
                        "keys order, longest, and starts_seconds. No Markdown."
                    ),
                ],
            }
        ],
    )
    recovery_receipt = post_json(base_url, recovery, timeout_s)
    semantic = (
        check_scene_answer(
            recovery_receipt.get("response"),
            expected_order=SCENE_ORDER,
            expected_longest="tie",
            expected_starts=SCENE_STARTS["order"],
        )
        if recovery_receipt.get("response_status") == 200
        else {
            "passed": False,
            "error": f"recovery HTTP status {recovery_receipt.get('response_status')}",
        }
    )
    passed = invalid_receipt.get("response_status") == 400 and bool(semantic.get("passed"))
    return {
        "case": "malformed-video-then-recovery",
        "steps": [
            {"step": "malformed", **invalid_receipt},
            {"step": "recovery", **recovery_receipt, "semantic": semantic},
        ],
        "passed": passed,
        "error": None if passed else "malformed request was not a 400 followed by a successful recovery",
    }


def concurrent_distinct(
    base_url: str,
    order: dict[str, Any],
    reverse: dict[str, Any],
    timeout_s: float,
) -> dict[str, Any]:
    bodies = {
        "order": request_body(
            "concurrent-order",
            [
                {
                    "role": "user",
                    "content": [
                        video_part(order),
                        text_part(
                            "Inspect the full video and return exactly one JSON object "
                            "with keys order, longest, and starts_seconds. No Markdown."
                        ),
                    ],
                }
            ],
        ),
        "reverse": request_body(
            "concurrent-reverse",
            [
                {
                    "role": "user",
                    "content": [
                        video_part(reverse),
                        text_part(
                            "Inspect the full video and return exactly one JSON object "
                            "with keys order, longest, and starts_seconds. No Markdown."
                        ),
                    ],
                }
            ],
        ),
    }
    zero = time.monotonic()
    with concurrent.futures.ThreadPoolExecutor(
        max_workers=2, thread_name_prefix="qwen-video"
    ) as pool:
        futures = {
            name: pool.submit(post_json, base_url, body, timeout_s, campaign_zero=zero)
            for name, body in bodies.items()
        }
        steps = {name: future.result() for name, future in futures.items()}
    for name, receipt in steps.items():
        expected = SCENE_ORDER if name == "order" else ["blue", "green", "red"]
        semantic = (
            check_scene_answer(
                receipt.get("response"),
                expected_order=expected,
                expected_longest="tie",
                expected_starts=SCENE_STARTS[name],
            )
            if receipt.get("response_status") == 200
            else {"passed": False, "error": f"HTTP status {receipt.get('response_status')}"}
        )
        receipt["case"] = f"concurrent-{name}"
        receipt["semantic"] = semantic
        receipt["passed"] = bool(semantic.get("passed"))
    return {
        "case": "concurrent-distinct-videos",
        "requests": steps,
        "passed": all(bool(step.get("passed")) for step in steps.values()),
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default=os.environ.get("ATLAS_BASE_URL", "http://127.0.0.1:8893"))
    parser.add_argument("--output", default=str(ROOT / "after" / "video-qualification.json"))
    parser.add_argument("--timeout-s", type=float, default=600.0)
    parser.add_argument("--generate-fixtures", action="store_true")
    parser.add_argument("--generate-only", action="store_true")
    parser.add_argument("--skip-procedure", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        if args.generate_fixtures:
            generate_auxiliary_fixtures()
        manifest = load_manifest()
        # Always verify every fixture before building a request. This makes a
        # stale or partially copied fixture set fail before touching serving.
        entries = {str(entry["name"]): find_fixture(str(entry["name"]), manifest) for entry in manifest}
        if args.generate_only:
            print(json.dumps({"generated": [fixture_receipt(entry) for entry in entries.values()]}, indent=2))
            return 0
        cases = build_cases(manifest, include_procedure=not args.skip_procedure)
        run_started = iso_now()
        results: list[dict[str, Any]] = []
        for case, body, checker in cases:
            results.append(run_single_case(case, body, checker, args.base_url, args.timeout_s))
        order = entries["order"]
        reverse = entries["reverse"]
        results.append(malformed_and_recovery(args.base_url, order, args.timeout_s))
        results.append(concurrent_distinct(args.base_url, order, reverse, args.timeout_s))
        passed = [result for result in results if result.get("passed")]
        failed = [result for result in results if not result.get("passed")]
        receipt = {
            "schema": SCHEMA,
            "model": MODEL,
            "base_url": args.base_url,
            "endpoint": args.base_url.rstrip("/") + "/v1/chat/completions",
            "started_at_utc": run_started,
            "finished_at_utc": iso_now(),
            "fixture_manifest_sha256": sha256_file(FIXTURES / "manifest.json"),
            "fixtures": [fixture_receipt(entry) for entry in entries.values()],
            "cases": results,
            "summary": {
                "total": len(results),
                "passed": len(passed),
                "failed": len(failed),
                "failed_cases": [result.get("case") for result in failed],
            },
        }
        destination = Path(args.output)
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(json.dumps(receipt, indent=2) + "\n")
        print(json.dumps(receipt["summary"], indent=2))
        return 0 if not failed else 1
    except HarnessError as exc:
        print(f"video_qualify: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
