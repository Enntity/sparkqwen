#!/usr/bin/env python3
# SPDX-License-Identifier: AGPL-3.0-only
"""Build the calibration and evaluation token sets for RadixArk/DaisyRose-27B (Qwen3.8-27B).

Adapted from experiments/sage-s21-flash-nvfp4-20261117/data/build_sets.py: the same
sources and seed, rendered with DaisyRose's tokenizer and chat template.

Deterministic and re-runnable: every source is pinned to a commit sha, every
choice is drawn from a seeded generator keyed by name, and every download is
cached under cache/ (a second run needs no network).

    cd <this folder>
    UV_CACHE_DIR="$PWD/cache/uv" uv run --no-project --with tokenizers --with 'jinja2>=3.1.6' \
        --with pyarrow --with requests python -I build_sets.py

Outputs (next to this file): eval.jsonl, calib.jsonl, MANIFEST.md, rows_used.json
and cache/render_samples.jsonl (chat rows with their messages, for the
transformers cross-check in test_sets.py).

All requests are anonymous: plain HTTPS GETs with no token, no cookie and no
netrc lookup, and nothing but the public file path in the URL.
"""
from __future__ import annotations

import argparse
import collections
import hashlib
import io
import json
import random
import re
import sys
import time
import zlib
from pathlib import Path

DATA = Path(__file__).resolve().parent
CACHE = DATA / "cache"
MODEL_DIR = CACHE / "model"

SEED = 20261117

MODEL_REPO = "RadixArk/DaisyRose-27B-NVFP4"
MODEL_REV = "c4d85c5dfad123426555c22f4e24bb15381f0bdb"
MODEL_FILES = ["tokenizer.json", "tokenizer_config.json", "chat_template.jinja", "generation_config.json"]

PLAIN_PREFIX = ""  # Qwen adds no BOS
THINK_END = 248069  # </think>

EVAL_MAX, EVAL_MIN, EVAL_PER_CATEGORY = 1152, 600, 32
CALIB_MAX, CALIB_MIN, CALIB_TOTAL = 2048, 256, 600_000

# Calibration mix in percent of tokens. A key is the group of categories that
# shares one line of the brief.
CALIB_TARGETS = {
    ("chat_reasoning",): 30,
    ("chat",): 15,
    ("tool_calling",): 12,
    ("code",): 15,
    ("prose_en", "science"): 10,
    ("prose_multilingual",): 13,
    ("math",): 5,
}
OTHER_LANGS = ["ja", "zh", "ko", "es", "fr", "de", "ru", "ar", "hi", "pt"]
CODE_LANGS = ["Python", "JavaScript", "TypeScript", "Java", "C", "C++", "GO", "Rust", "C#", "PHP", "Ruby", "Shell"]
PERMISSIVE = {"mit", "apache-2.0", "bsd-2-clause", "bsd-3-clause", "isc", "unlicense", "cc0-1.0"}
# Sources that feed both sets are split by row index before anything is chosen:
# rows whose index in the file is a multiple of 5 can only go to evaluation,
# all other rows only to calibration. (Math uses the test and train splits.)
EVAL_MODULUS = 5


def eval_row(index):
    return index % EVAL_MODULUS == 0


MATH_SUBJECTS = [
    "algebra", "counting_and_probability", "geometry", "intermediate_algebra",
    "number_theory", "prealgebra", "precalculus",
]

# Every source, pinned. `licence` is what the dataset card states.
SOURCES = {
    "openthoughts": {
        "dataset": "open-thoughts/OpenThoughts-114k",
        "revision": "bd093c3994fd54d2390985b66988ddf282a55eb6",
        "licence": "apache-2.0",
    },
    "ultrachat": {
        "dataset": "HuggingFaceH4/ultrachat_200k",
        "revision": "8049631c405ae6576f93f445c6b8166f76f5505a",
        "licence": "mit",
    },
    "glaive": {
        # The repo's own file is one 271 MB JSON; this is the Hub's automatic
        # parquet conversion of it (branch refs/convert/parquet), pinned by sha.
        "dataset": "glaiveai/glaive-function-calling-v2",
        "revision": "8862406ff857565709af3dca7fed589b84edf235",
        "licence": "apache-2.0",
        "note": "refs/convert/parquet of main e7f4b6456019f5d8bcb991ef0dd67d8ff23221ac",
    },
    "code": {
        "dataset": "codeparrot/github-code-clean",
        "revision": "c48d40f9e70f0196f8236901ee35807f7d6c44c0",
        "licence": "apache-2.0 on the card; each file carries its repository licence, "
        "only mit/apache-2.0/bsd/isc/unlicense/cc0-1.0 files are used",
    },
    "wikipedia": {
        "dataset": "wikimedia/wikipedia",
        "revision": "b04c8d1ceb2f5cd4588862100d08de323dccfbaa",
        "licence": "cc-by-sa-3.0 and gfdl",
    },
    "arxiv": {
        "dataset": "common-pile/arxiv_papers",
        "revision": "963fe980c55b353980653f1a27c1dc0c8a2d7058",
        "licence": "no licence field on the card; the card says it holds only papers under "
        "CC BY, CC BY-SA and CC0, with the licence in each row's metadata",
    },
    "pubmed": {
        "dataset": "common-pile/pubmed",
        "revision": "648b8cfc93953ca0663a9c96a8d842a91b98fb64",
        "licence": "no licence field on the card; the card says it holds only papers under "
        "CC BY, CC BY-SA and CC0, with the licence in each row's metadata",
    },
    "math": {
        "dataset": "EleutherAI/hendrycks_math",
        "revision": "21a5633873b6a120296cce3e2df9d5550074f4a3",
        "licence": "mit",
    },
}

WIKI_SHARDS = {
    "en": 41, "ja": 15, "zh": 6, "ko": 3, "es": 13, "fr": 17, "de": 20, "ru": 21, "ar": 7, "hi": 2, "pt": 6,
}
WIKI_ROW_GROUPS = [0, 40]  # 1,000 articles each, from the first shard of a language

# (file, row groups) per reasoning domain. The metadata config is sorted by
# source, so each domain lives in known row groups.
OT_FILES = {
    "math": [
        ("metadata/train-00000-of-00012.parquet", [0]),
        ("metadata/train-00002-of-00012.parquet", [3]),
        ("metadata/train-00004-of-00012.parquet", [7]),
        ("metadata/train-00005-of-00012.parquet", [5]),
        ("metadata/train-00007-of-00012.parquet", [2]),
        ("metadata/train-00008-of-00012.parquet", [9]),
    ],
    "code": [
        ("metadata/train-00009-of-00012.parquet", [6, 8]),  # code_contests
        ("metadata/train-00010-of-00012.parquet", [2, 7]),  # apps, taco
        ("metadata/train-00011-of-00012.parquet", [3]),  # codeforces
    ],
    "science": [("metadata/train-00011-of-00012.parquet", [5, 6, 7])],  # biology, physics, chemistry
}
OT_COLUMNS = ["problem", "deepseek_reasoning", "deepseek_solution", "domain", "source"]

CODE_FILES = [
    ("data/train-00000-of-00880.parquet", [0]),
    ("data/train-00293-of-00880.parquet", [0]),
    ("data/train-00586-of-00880.parquet", [0]),
    ("data/train-00879-of-00880.parquet", [0]),
]
SCIENCE_FILES = {
    "arxiv": [("00000_arxiv-papers.jsonl.gz", 6_000_000), ("00012_arxiv-papers.jsonl.gz", 6_000_000)],
    "pubmed": [("data/00000_pubmedcentral.jsonl.gz", 6_000_000), ("data/00010_pubmedcentral.jsonl.gz", 6_000_000)],
}


# ------------------------------------------------------------------ fetching


def _session():
    import requests

    s = requests.Session()
    s.trust_env = False  # no netrc, no environment credentials or proxies
    s.headers.update({"User-Agent": "python-requests"})
    return s


def _get(session, url, headers=None, tries=5):
    for attempt in range(tries):
        try:
            r = session.get(url, headers=headers or {}, timeout=120)
            if r.status_code in (200, 206):
                return r
            if r.status_code in (401, 403, 404):
                r.raise_for_status()
        except Exception:  # noqa: BLE001 - retry any transport error
            if attempt == tries - 1:
                raise
        time.sleep(2 * (attempt + 1))
    raise RuntimeError(f"could not fetch {url}")


def _atomic_write(path: Path, data: bytes):
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".part")
    tmp.write_bytes(data)
    tmp.replace(path)


def _hf_url(kind, repo, rev, path):
    prefix = "datasets/" if kind == "dataset" else ""
    return f"https://huggingface.co/{prefix}{repo}/resolve/{rev}/{path}"


class HttpFile(io.RawIOBase):
    """Read-only seekable file over HTTP range requests (for parquet footers and row groups)."""

    def __init__(self, url):
        self.session = _session()
        r = self.session.head(url, allow_redirects=True, timeout=120)
        r.raise_for_status()
        self.url = r.url
        self.size = int(r.headers["Content-Length"])
        self.pos = 0

    def seekable(self):
        return True

    def readable(self):
        return True

    def tell(self):
        return self.pos

    def seek(self, offset, whence=0):
        self.pos = offset if whence == 0 else (self.pos + offset if whence == 1 else self.size + offset)
        return self.pos

    def read(self, n=-1):
        if n < 0:
            n = self.size - self.pos
        if n == 0:
            return b""
        r = _get(self.session, self.url, {"Range": f"bytes={self.pos}-{self.pos + n - 1}"})
        self.pos += len(r.content)
        return r.content

    def readinto(self, b):
        data = self.read(len(b))
        b[: len(data)] = data
        return len(data)


def ensure_model_files():
    s = None
    for name in MODEL_FILES:
        path = MODEL_DIR / name
        if not path.exists():
            s = s or _session()
            _atomic_write(path, _get(s, _hf_url("model", MODEL_REPO, MODEL_REV, name)).content)


def source_id(key, path):
    src = SOURCES[key]
    return f"{src['dataset']}@{src['revision']}:{path}"


def fetch_row_groups(key, path, row_groups, columns):
    """Rows of the given parquet row groups (None = all) as dicts, with `_row` = index in the file."""
    import pyarrow as pa
    import pyarrow.parquet as pq

    src = SOURCES[key]
    tag = "all" if row_groups is None else "rg" + "-".join(map(str, row_groups))
    cols = hashlib.sha1(",".join(columns).encode()).hexdigest()[:8]
    cached = CACHE / "hf" / src["dataset"] / src["revision"] / f"{path}.{tag}.{cols}.parquet"
    if not cached.exists():
        print(f"  fetching {src['dataset']} {path} {tag}", file=sys.stderr)
        f = HttpFile(_hf_url("dataset", src["dataset"], src["revision"], path))
        pf = pq.ParquetFile(f)
        md = pf.metadata
        starts, total = [], 0
        for i in range(md.num_row_groups):
            starts.append(total)
            total += md.row_group(i).num_rows
        wanted = list(range(md.num_row_groups)) if row_groups is None else row_groups
        tables = []
        for rg in wanted:
            t = pf.read_row_group(rg, columns=columns)
            t = t.append_column("_row", pa.array(range(starts[rg], starts[rg] + t.num_rows), pa.int64()))
            tables.append(t)
        cached.parent.mkdir(parents=True, exist_ok=True)
        tmp = cached.with_name(cached.name + ".part")
        pq.write_table(pa.concat_tables(tables), tmp)
        tmp.replace(cached)
    return pq.read_table(cached).to_pylist()


def fetch_gz_prefix(key, path, nbytes):
    """Complete JSON lines found in the first `nbytes` of a .jsonl.gz, with `_row` = line index."""
    src = SOURCES[key]
    cached = CACHE / "hf" / src["dataset"] / src["revision"] / f"{path}.first{nbytes}"
    if not cached.exists():
        print(f"  fetching {src['dataset']} {path} first {nbytes} bytes", file=sys.stderr)
        url = _hf_url("dataset", src["dataset"], src["revision"], path)
        r = _get(_session(), url, {"Range": f"bytes=0-{nbytes - 1}"})
        if len(r.content) != nbytes:
            raise RuntimeError(f"expected {nbytes} bytes of {path}, got {len(r.content)}")
        _atomic_write(cached, r.content)
    raw = zlib.decompressobj(16 + zlib.MAX_WBITS).decompress(cached.read_bytes())
    rows = []
    for i, line in enumerate(raw.split(b"\n")[:-1]):  # the last piece is cut mid-line
        row = json.loads(line)
        row["_row"] = i
        rows.append(row)
    return rows


# ------------------------------------------------------- tokenizer, template

_TOKENIZER = None
_TEMPLATE = None
_CONTROL_STRINGS = None


def load_tokenizer():
    global _TOKENIZER
    if _TOKENIZER is None:
        from tokenizers import Tokenizer

        ensure_model_files()
        _TOKENIZER = Tokenizer.from_file(str(MODEL_DIR / "tokenizer.json"))
    return _TOKENIZER


def encode(tok, text):
    # add_special_tokens=False is what transformers' apply_chat_template uses.
    return tok.encode(text, add_special_tokens=False).ids


def control_strings():
    """Every added-token string of the tokenizer; source text containing one is rejected."""
    global _CONTROL_STRINGS
    if _CONTROL_STRINGS is None:
        ensure_model_files()
        added = json.loads((MODEL_DIR / "tokenizer.json").read_text())["added_tokens"]
        _CONTROL_STRINGS = [a["content"] for a in added]
    return _CONTROL_STRINGS


def has_control_text(text):
    return any(c in text for c in control_strings())


def _tojson(x, ensure_ascii=False, indent=None, separators=None, sort_keys=False):
    # Same as the filter transformers installs (no HTML escaping, unlike jinja2's own).
    return json.dumps(x, ensure_ascii=ensure_ascii, indent=indent, separators=separators, sort_keys=sort_keys)


def _raise_exception(message):
    import jinja2

    raise jinja2.exceptions.TemplateError(message)


def _strftime_now(fmt):
    import datetime

    return datetime.datetime.now().strftime(fmt)


def load_template():
    """chat_template.jinja compiled the way transformers compiles it."""
    global _TEMPLATE
    if _TEMPLATE is None:
        import jinja2.ext
        from jinja2.sandbox import ImmutableSandboxedEnvironment

        ensure_model_files()
        env = ImmutableSandboxedEnvironment(
            trim_blocks=True, lstrip_blocks=True, extensions=[jinja2.ext.loopcontrols]
        )
        env.filters["tojson"] = _tojson
        env.globals["raise_exception"] = _raise_exception
        env.globals["strftime_now"] = _strftime_now
        _TEMPLATE = env.from_string((MODEL_DIR / "chat_template.jinja").read_text())
    return _TEMPLATE


def render_chat(messages, tools=None, add_generation_prompt=False, **kwargs):
    """Render like tokenizer.apply_chat_template(..., tokenize=False)."""
    return load_template().render(
        messages=messages,
        tools=tools,
        documents=None,
        add_generation_prompt=add_generation_prompt,
        eos_token="<|endoftext|>",
        pad_token="<|endoftext|>",
        **kwargs,
    )


# ----------------------------------------------------------------- examples


def rng_for(*parts):
    return random.Random(":".join([str(SEED), *map(str, parts)]))


def shuffled(rows, *name):
    rows = list(rows)
    rng_for("shuffle", *name).shuffle(rows)
    return rows


def cut(tok, ids, max_tokens):
    """First max_tokens ids, minus trailing tokens that would end the text inside a character."""
    ids = ids[:max_tokens]
    while ids and tok.decode(ids[-4:], skip_special_tokens=False).endswith("\ufffd"):
        ids = ids[:-1]
    return ids


def plain_ids(tok, text, max_tokens, rng=None):
    """Token ids of one window of a plain document, or None if the text is unusable.

    With `rng`, half of the documents longer than the window start at a random
    line instead of at the top (calibration only).
    """
    text = text.strip()
    if not text or has_control_text(text):
        return None
    enc = tok.encode(PLAIN_PREFIX + text, add_special_tokens=False)
    ids, window = enc.ids, "whole"
    if len(ids) > max_tokens:
        window = "head"
        if rng is not None and rng.random() < 0.5:
            start = rng.randrange(2, len(ids) - max_tokens + 2)
            char = enc.offsets[start][0] - len(PLAIN_PREFIX)
            newline = text.find("\n", max(char, 0))
            if newline != -1:
                later = encode(tok, PLAIN_PREFIX + text[newline + 1 :].lstrip("\n"))
                if len(later) >= max_tokens:
                    ids, window = later, "offset"
    return cut(tok, ids, max_tokens), window, len(ids)


def chat_ids(tok, messages, tools, effort, max_tokens, trim_turns=False):
    """Ids of a rendered conversation cut to max_tokens.

    Returns (ids, truncated, messages_used) with truncated one of none/turns/tokens.
    With trim_turns, whole trailing user/assistant exchanges are dropped first.
    """
    kw = {"reasoning_effort": effort} if effort else {}
    truncated = "none"
    while True:
        ids = encode(tok, render_chat(messages, tools=tools, **kw))
        if len(ids) <= max_tokens:
            return ids, truncated, messages
        if trim_turns and len(messages) > 2:
            messages = messages[:-1]
            while len(messages) > 2 and messages[-1]["role"] != "assistant":
                messages = messages[:-1]
            truncated = "turns"
            continue
        return cut(tok, ids, max_tokens), "tokens", messages


def make_row(category, lang, key, path, rows, ids, **extra):
    row = {
        "id": None,
        "category": category,
        "lang": lang,
        "source": source_id(key, path),
        "source_row": rows[0],
        "source_rows": list(rows),
        "n_tokens": len(ids),
        "input_ids": ids,
    }
    row.update(extra)
    return row


class Used:
    """Source rows already taken, so no row is used twice or in both sets."""

    def __init__(self):
        self.seen = set()

    def free(self, key, path, rows):
        sid = source_id(key, path)
        return all((sid, r) not in self.seen for r in rows)

    def take(self, key, path, rows):
        sid = source_id(key, path)
        for r in rows:
            assert (sid, r) not in self.seen
            self.seen.add((sid, r))


# ------------------------------------------------------------ source readers


def wiki_pool(lang):
    path = f"20231101.{lang}/train-00000-of-{WIKI_SHARDS[lang]:05d}.parquet"
    rows = fetch_row_groups("wikipedia", path, WIKI_ROW_GROUPS, ["title", "text"])
    return path, shuffled(rows, "wikipedia", lang)


def wiki_text(row):
    return f"{row['title']}\n\n{row['text']}"


def code_pool():
    """{language: [(path, row), ...]} of permissively licensed, hand-written-looking files."""
    by_lang = collections.defaultdict(list)
    for path, rgs in CODE_FILES:
        for row in fetch_row_groups("code", path, rgs, ["code", "language", "license", "size"]):
            if row["language"] not in CODE_LANGS or row["license"] not in PERMISSIVE:
                continue
            code = row["code"]
            if not 1_500 <= len(code) <= 80_000:
                continue
            lines = code.split("\n")
            if max(map(len, lines)) > 240 or len(lines) < 30:
                continue
            by_lang[row["language"]].append((path, row))
    return {lang: shuffled(by_lang[lang], "code", lang) for lang in CODE_LANGS}


def science_pool(key):
    out = []
    for path, nbytes in SCIENCE_FILES[key]:
        for row in fetch_gz_prefix(key, path, nbytes):
            if len(row["text"]) >= 6_000:
                out.append((path, row))
    return shuffled(out, "science", key)


def math_pool(split):
    """{subject: (path, rows)} of problem/solution pairs."""
    pools = {}
    for subject in MATH_SUBJECTS:
        path = f"{subject}/{split}-00000-of-00001.parquet"
        rows = fetch_row_groups("math", path, None, ["problem", "solution"])
        pools[subject] = (path, shuffled(rows, "math", split, subject))
    return pools


def math_block(row):
    return f"Problem:\n{row['problem'].strip()}\n\nSolution:\n{row['solution'].strip()}"


def math_docs(tok, pools, max_tokens, fill, used):
    """Yield (path, row indices, ids): several problems of one subject joined into a document.

    fill="cut": add problems until the document passes max_tokens, then cut (evaluation).
    fill="fit": stop before the problem that would pass max_tokens (calibration).
    """
    cursors = {s: 0 for s in MATH_SUBJECTS}
    while True:
        progressed = False
        for subject in MATH_SUBJECTS:
            path, rows = pools[subject]
            blocks, picked, ids = [], [], []
            i = cursors[subject]
            while i < len(rows):
                row = rows[i]
                i += 1
                block = math_block(row)
                if has_control_text(block) or not used.free("math", path, [row["_row"]]):
                    continue
                trial = encode(tok, PLAIN_PREFIX + "\n\n".join(blocks + [block]))
                if fill == "fit" and len(trial) > max_tokens:
                    if blocks:
                        i -= 1  # leave it for the next document
                        break
                    continue  # a single problem longer than the window: skip it
                blocks.append(block)
                picked.append(row["_row"])
                ids = trial
                if len(ids) >= max_tokens:
                    break
            cursors[subject] = i
            if picked and (fill == "fit" or len(ids) >= max_tokens):
                progressed = True
                yield path, picked, cut(tok, ids, max_tokens)
        if not progressed:
            return


def reasoning_pool(domain):
    out = []
    for path, rgs in OT_FILES[domain]:
        for row in fetch_row_groups("openthoughts", path, rgs, OT_COLUMNS):
            wanted = {"math": {"math"}, "code": {"code"}, "science": {"biology", "physics", "chemistry"}}[domain]
            if row["domain"] in wanted:
                out.append((path, row))
    return shuffled(out, "openthoughts", domain)


def reasoning_messages(row):
    problem = (row["problem"] or "").strip()
    reasoning = (row["deepseek_reasoning"] or "").strip()
    answer = (row["deepseek_solution"] or "").strip()
    if not problem or not reasoning or not answer:
        return None
    if has_control_text(problem) or has_control_text(reasoning) or has_control_text(answer):
        return None
    return [
        {"role": "user", "content": problem},
        {"role": "assistant", "reasoning_content": reasoning, "content": answer},
    ]


def ultrachat_pool():
    path = "data/train_sft-00000-of-00003-a3ecf92756993583.parquet"
    rows = fetch_row_groups("ultrachat", path, [0, 35], ["messages"])
    return path, shuffled(rows, "ultrachat")


def ultrachat_messages(row):
    messages = [{"role": m["role"], "content": m["content"].strip()} for m in row["messages"]]
    if len(messages) < 4 or len(messages) % 2:
        return None
    for i, m in enumerate(messages):
        if m["role"] != ("user", "assistant")[i % 2] or not m["content"] or has_control_text(m["content"]):
            return None
    return messages


GLAIVE_PATH = "default/train/0000.parquet"
_GLAIVE_TURN = re.compile(r"(?:^|\n+)(USER|ASSISTANT|FUNCTION RESPONSE): ")
_GLAIVE_CALL = re.compile(r"^\{\s*\"name\":\s*\"([^\"]+)\",\s*\"arguments\":\s*'(.*)'\s*\}$", re.S)


def glaive_pool():
    rows = fetch_row_groups("glaive", GLAIVE_PATH, list(range(20)), ["system", "chat"])
    return GLAIVE_PATH, shuffled(rows, "glaive")


def parse_glaive(row):
    """Glaive's text format -> (messages, tools) in OpenAI shape, or None if it does not parse cleanly."""
    system, chat = row["system"], row["chat"]
    marker = "Use them if required -"
    if marker not in system:
        return None
    tools, rest, dec = [], system.split(marker, 1)[1].strip(), json.JSONDecoder()
    try:
        while rest:
            fn, end = dec.raw_decode(rest)
            if not isinstance(fn, dict) or not isinstance(fn.get("name"), str):
                return None
            tools.append({"type": "function", "function": fn})
            rest = rest[end:].strip()
    except json.JSONDecodeError:
        return None
    if not tools:
        return None
    names = {t["function"]["name"] for t in tools}

    parts = _GLAIVE_TURN.split(chat)
    if parts[0].strip():
        return None
    messages, calls, pending = [], 0, None
    for role, text in zip(parts[1::2], parts[2::2]):
        text = text.replace("<|endoftext|>", "").strip()
        if has_control_text(text):
            return None
        if role == "USER":
            if pending or not text:
                return None
            messages.append({"role": "user", "content": text})
        elif role == "ASSISTANT":
            if pending:
                return None
            if "<functioncall>" in text:
                before, call = text.split("<functioncall>", 1)
                m = _GLAIVE_CALL.match(call.strip())
                if not m or m.group(1) not in names:
                    return None
                try:
                    arguments = json.loads(m.group(2))
                except json.JSONDecodeError:
                    return None
                if not isinstance(arguments, dict):
                    return None
                pending = f"call_{calls}"
                calls += 1
                messages.append({
                    "role": "assistant",
                    "content": before.strip(),
                    "tool_calls": [{
                        "id": pending,
                        "type": "function",
                        "function": {"name": m.group(1), "arguments": arguments},
                    }],
                })
            else:
                if not text:
                    return None
                messages.append({"role": "assistant", "content": text})
        else:  # FUNCTION RESPONSE
            if not pending or not text:
                return None
            messages.append({"role": "tool", "tool_call_id": pending, "content": text})
            pending = None
    if pending or not calls or not messages or messages[0]["role"] != "user" or messages[-1]["role"] != "assistant":
        return None
    return messages, tools


# ---------------------------------------------------------------- the sets


def build_eval(tok, used, samples):
    rows = []

    def add(category, lang, key, path, src_rows, ids, **extra):
        assert EVAL_MIN <= len(ids) <= EVAL_MAX
        used.take(key, path, src_rows)
        row = make_row(category, lang, key, path, src_rows, ids, **extra)
        n = sum(1 for r in rows if r["category"] == category)
        row["id"] = f"eval-{category}-{n:03d}"
        rows.append(row)
        return row

    # code: full 1,152-token heads, round-robin over the languages
    pools = code_pool()
    cursors = collections.Counter()
    n = 0
    while n < EVAL_PER_CATEGORY:
        lang = CODE_LANGS[n % len(CODE_LANGS)]
        while True:
            path, row = pools[lang][cursors[lang]]
            cursors[lang] += 1
            if not eval_row(row["_row"]):
                continue
            got = plain_ids(tok, row["code"], EVAL_MAX)
            if got and got[2] >= EVAL_MAX:
                add("code", lang.lower(), "code", path, [row["_row"]], got[0],
                    licence=row["license"], window=got[1])
                break
        n += 1

    # English and Japanese prose
    for category, lang in (("prose_en", "en"), ("prose_ja", "ja")):
        path, pool = wiki_pool(lang)
        n = 0
        for row in pool:
            if not eval_row(row["_row"]):
                continue
            got = plain_ids(tok, wiki_text(row), EVAL_MAX)
            if got and got[2] >= EVAL_MAX:
                add(category, lang, "wikipedia", path, [row["_row"]], got[0], window=got[1])
                n += 1
                if n == EVAL_PER_CATEGORY:
                    break
        assert n == EVAL_PER_CATEGORY

    # math: several test-split problems of one subject per document
    docs = math_docs(tok, math_pool("test"), EVAL_MAX, "cut", used)
    for _ in range(EVAL_PER_CATEGORY):
        path, picked, ids = next(docs)
        add("math", "en", "math", path, picked, ids, window="head")

    # science: paper heads, half arXiv and half PubMed Central
    for key in ("arxiv", "pubmed"):
        n = 0
        for path, row in science_pool(key):
            if not eval_row(row["_row"]):
                continue
            got = plain_ids(tok, row["text"], EVAL_MAX)
            if got and got[2] >= EVAL_MAX:
                add("science", "en", key, path, [row["_row"]], got[0],
                    licence=row["metadata"]["license"], window=got[1])
                n += 1
                if n == EVAL_PER_CATEGORY // 2:
                    break
        assert n == EVAL_PER_CATEGORY // 2

    # chat with visible reasoning. Most traces are far longer than the window
    # (median 2,200 to 6,400 tokens by domain), so half of the documents are
    # whole conversations that fit and half are typical ones cut at 1,152.
    quota = {"code": (6, 5), "math": (5, 6), "science": (5, 5)}  # (whole, cut)
    for domain, (want_whole, want_cut) in quota.items():
        whole = cut = 0
        for path, row in reasoning_pool(domain):
            if whole == want_whole and cut == want_cut:
                break
            if not eval_row(row["_row"]):
                continue
            messages = reasoning_messages(row)
            if not messages:
                continue
            ids, truncated, _ = chat_ids(tok, messages, None, None, EVAL_MAX)
            if truncated == "none":
                if len(ids) < EVAL_MIN or whole == want_whole:
                    continue
                whole += 1
            else:
                if cut == want_cut:
                    continue
                cut += 1
            out = add("chat_reasoning", "en", "openthoughts", path, [row["_row"]], ids,
                      domain=domain, truncated=truncated, reasoning_effort=None)
            samples.append({"id": out["id"], "messages": messages, "tools": None, "reasoning_effort": None,
                            "n_tokens": len(ids), "input_ids": ids})
        assert (whole, cut) == (want_whole, want_cut), (domain, whole, cut)

    # tool calling: whole conversations that fit the window
    path, pool = glaive_pool()
    n = 0
    for row in pool:
        if not eval_row(row["_row"]):
            continue
        parsed = parse_glaive(row)
        if not parsed:
            continue
        messages, tools = parsed
        ids, truncated, _ = chat_ids(tok, messages, tools, None, EVAL_MAX)
        if truncated != "none" or len(ids) < EVAL_MIN:
            continue
        out = add("tool_calling", "en", "glaive", path, [row["_row"]], ids,
                  truncated=truncated, reasoning_effort=None)
        samples.append({"id": out["id"], "messages": messages, "tools": tools, "reasoning_effort": None,
                        "n_tokens": len(ids), "input_ids": ids})
        n += 1
        if n == EVAL_PER_CATEGORY:
            break
    assert n == EVAL_PER_CATEGORY
    return rows


def build_calib(tok, used, samples):
    rows = []
    counts = collections.Counter()
    budget = {c: CALIB_TOTAL * share / 100 for group, share in CALIB_TARGETS.items() for c in group}
    budget["prose_en"] = budget["science"] = CALIB_TOTAL * 0.05

    def add(category, lang, key, path, src_rows, ids, **extra):
        assert CALIB_MIN <= len(ids) <= CALIB_MAX
        used.take(key, path, src_rows)
        row = make_row(category, lang, key, path, src_rows, ids, **extra)
        row["id"] = f"calib-{category}-{counts[category]:04d}"
        counts[category] += 1
        rows.append(row)
        return row

    def sample(out, messages, tools, effort, limit=40):
        if sum(1 for s in samples if s["id"].startswith(f"calib-{out['category']}-")) < limit:
            samples.append({"id": out["id"], "messages": messages, "tools": tools, "reasoning_effort": effort,
                            "n_tokens": out["n_tokens"], "input_ids": out["input_ids"]})

    # --- chat with reasoning: a third each of code, math and science questions.
    # Conversations longer than the window are cut at 2,048 tokens (they end
    # inside the reasoning); at most half of a domain's tokens come from those.
    per_domain = budget["chat_reasoning"] / 3
    for domain in ("code", "math", "science"):
        total = cut = 0
        for path, row in reasoning_pool(domain):
            if total >= per_domain:
                break
            if eval_row(row["_row"]) or not used.free("openthoughts", path, [row["_row"]]):
                continue
            messages = reasoning_messages(row)
            if not messages:
                continue
            effort = rng_for("effort", "openthoughts", path, row["_row"]).choice([None, "medium"])
            ids, truncated, _ = chat_ids(tok, messages, None, effort, CALIB_MAX)
            if len(ids) < CALIB_MIN:
                continue
            if truncated != "none":
                if cut + len(ids) > per_domain / 2:
                    continue
                cut += len(ids)
            total += len(ids)
            out = add("chat_reasoning", "en", "openthoughts", path, [row["_row"]], ids,
                      domain=domain, truncated=truncated, reasoning_effort=effort)
            sample(out, messages, None, effort)
        assert total >= per_domain, (domain, total)

    # --- plain multi-turn chat
    path, pool = ultrachat_pool()
    total = 0
    for row in pool:
        if total >= budget["chat"]:
            break
        messages = ultrachat_messages(row)
        if not messages:
            continue
        effort = rng_for("effort", "ultrachat", row["_row"]).choice([None, "medium", "low"])
        ids, truncated, kept = chat_ids(tok, messages, None, effort, CALIB_MAX, trim_turns=True)
        if len(ids) < CALIB_MIN or truncated == "tokens":
            continue
        total += len(ids)
        out = add("chat", "en", "ultrachat", path, [row["_row"]], ids,
                  truncated=truncated, reasoning_effort=effort)
        sample(out, kept, None, effort)
    assert total >= budget["chat"]

    # --- tool calling
    path, pool = glaive_pool()
    total = 0
    for row in pool:
        if total >= budget["tool_calling"]:
            break
        if eval_row(row["_row"]) or not used.free("glaive", path, [row["_row"]]):
            continue
        parsed = parse_glaive(row)
        if not parsed:
            continue
        messages, tools = parsed
        effort = rng_for("effort", "glaive", row["_row"]).choice([None, "medium", "low"])
        ids, truncated, _ = chat_ids(tok, messages, tools, effort, CALIB_MAX)
        if len(ids) < CALIB_MIN or truncated != "none":
            continue
        total += len(ids)
        out = add("tool_calling", "en", "glaive", path, [row["_row"]], ids,
                  truncated=truncated, reasoning_effort=effort)
        sample(out, messages, tools, effort)
    assert total >= budget["tool_calling"]

    # --- source code, the same token budget for each language
    pools = code_pool()
    for lang in CODE_LANGS:
        total = 0
        for path, row in pools[lang]:
            if total >= budget["code"] / len(CODE_LANGS):
                break
            if eval_row(row["_row"]) or not used.free("code", path, [row["_row"]]):
                continue
            got = plain_ids(tok, row["code"], CALIB_MAX, rng_for("window", "code", path, row["_row"]))
            if not got or len(got[0]) < CALIB_MIN:
                continue
            total += len(got[0])
            add("code", lang.lower(), "code", path, [row["_row"]], got[0], licence=row["license"], window=got[1])
        assert total >= budget["code"] / len(CODE_LANGS), (lang, total)

    # --- English prose
    def wiki(category, lang, want):
        path, pool = wiki_pool(lang)
        total = 0
        for row in pool:
            if total >= want:
                break
            if eval_row(row["_row"]) or not used.free("wikipedia", path, [row["_row"]]):
                continue
            got = plain_ids(tok, wiki_text(row), CALIB_MAX, rng_for("window", "wikipedia", path, row["_row"]))
            if not got or len(got[0]) < CALIB_MIN:
                continue
            total += len(got[0])
            add(category, lang, "wikipedia", path, [row["_row"]], got[0], window=got[1])
        assert total >= want, (lang, total)

    wiki("prose_en", "en", budget["prose_en"])

    # --- scientific text, half arXiv and half PubMed Central
    for key in ("arxiv", "pubmed"):
        total = 0
        for path, row in science_pool(key):
            if total >= budget["science"] / 2:
                break
            if eval_row(row["_row"]) or not used.free(key, path, [row["_row"]]):
                continue
            got = plain_ids(tok, row["text"], CALIB_MAX, rng_for("window", key, path, row["_row"]))
            if not got or len(got[0]) < CALIB_MIN:
                continue
            total += len(got[0])
            add("science", "en", key, path, [row["_row"]], got[0],
                licence=row["metadata"]["license"], window=got[1])
        assert total >= budget["science"] / 2

    # --- other languages, the same token budget for each
    for lang in OTHER_LANGS:
        wiki("prose_multilingual", lang, budget["prose_multilingual"] / len(OTHER_LANGS))

    # --- math: several train-split problems of one subject per document
    total = 0
    for path, picked, ids in math_docs(tok, math_pool("train"), CALIB_MAX, "fit", used):
        if total >= budget["math"]:
            break
        if len(ids) < CALIB_MIN:
            continue
        total += len(ids)
        add("math", "en", "math", path, picked, ids, window="whole")
    assert total >= budget["math"]
    return rows


# ----------------------------------------------------------------- manifest

DEVIATIONS = """\
Evaluation set

1. Reasoning chat is half whole, half cut. OpenThoughts reasoning traces are long: the rendered
   conversation has a median of about 5,600 tokens for math, 6,400 for code and 2,200 for science,
   and only 1 to 2 in 100 fit in 600 to 1,152 tokens. Taking only conversations that fit would have
   meant only the easiest questions. So 16 documents are whole conversations (reasoning, `</think>`,
   answer; 6 code, 5 math, 5 science) and 16 are ordinary conversations cut at 1,152 tokens (5 code,
   6 math, 5 science); most of those end inside the reasoning, a few reach `</think>` and are cut
   in the answer (counts in the table above). The `truncated` field says which is which (`none` or
   `tokens`).
2. Tool-calling documents are the long tail of Glaive. With the template's tools preamble a Glaive
   conversation has a median of about 375 tokens; only 2 to 3% reach the 600-token floor. All 32
   are whole conversations, but they are the longest ones (more turns or more tool schemas).
3. Math documents are several problems joined together. A Hendrycks MATH row (problem + solution)
   is about 250 tokens, so each document is `Problem:\\n...\\n\\nSolution:\\n...` blocks from one
   subject, joined by blank lines until the text passes 1,152 tokens, then cut. The last solution
   of each document is therefore cut short. Evaluation uses the test split and calibration the
   train split.
4. All plain evaluation documents are exactly 1,152 tokens (sources shorter than that were skipped),
   to line up with the published comparison's roughly 1,127 scored positions per document. They are
   the head of the source: code files often begin with a licence header.
5. Science is 16 arXiv papers and 16 PubMed Central papers, full text from the top.

Calibration set

6. "English prose and scientific text" (10%) is split evenly into two categories, `prose_en`
   (English Wikipedia) and `science` (half arXiv, half PubMed Central full text).
7. Reasoning chat is a third each of code, math and science questions. Because most traces are
   longer than 2,048 tokens, at most half of each domain's tokens come from conversations cut at
   2,048 (most end inside the reasoning); the rest are whole conversations, which over-represents
   short traces compared with the dataset.
8. `reasoning_effort` is varied in calibration so that all three system lines the template can emit
   are seen: reasoning chat draws from unset/`high`, plain chat and tool calling from
   unset/`high`/`low`. Unset renders as `Reasoning Effort: Max` (the template has no way to omit
   the line). Evaluation always leaves it unset. The value is in each chat row's `reasoning_effort`.
9. Plain chat (UltraChat) and tool calling (Glaive) carry no reasoning, so every assistant turn in
   them renders as `<think></think>` followed by the answer, which is what the template emits for an
   assistant turn without `reasoning_content`. Only the OpenThoughts rows have non-empty reasoning.
10. A plain chat longer than 2,048 tokens loses whole trailing user/assistant exchanges until it fits,
    rather than being cut mid-turn (`truncated` = `turns`).
11. Half of the plain documents longer than the window start at a random line of the source instead
    of at the top (`window` = `offset`); still one window per source document.
12. Math documents are joined problems as in the evaluation set, but a document stops before the
    problem that would pass 2,048 tokens, so nothing is cut.

Sources

13. Science comes from `common-pile/arxiv_papers` and `common-pile/pubmed`. Their shards are 0.3 to
    2.8 GB gzip files, so only the first 6,000,000 bytes of two shards each are fetched and the
    complete lines in them used; these are the earliest papers of each shard. Neither card has a
    licence field; both say the collection is limited to CC BY, CC BY-SA and CC0 papers and give the
    licence per row, which is copied into each row's `licence`. The arXiv text is LaTeX converted to
    plain text and carries conversion noise (footnote digits glued to words, tables of contents);
    the PubMed text is markdown with anchors such as `{#s1}`.
14. Code comes from `codeparrot/github-code-clean` (not gated, has a per-file licence column), four
    row groups from four shards. Only files whose repository licence is MIT, Apache-2.0, BSD, ISC,
    Unlicense or CC0 are used (GPL, MPL and the rest are dropped), in twelve languages with equal
    token budgets: Python, JavaScript, TypeScript, Java, C, C++, Go, Rust, C#, PHP, Ruby, Shell.
    Files under 1,500 or over 80,000 characters, under 30 lines, or with a line over 240 characters
    are dropped. The licence column is the dataset's claim about the repository; a few files carry
    a different licence in their own header.
15. Glaive is read from the Hub's parquet conversion of the dataset's single JSON file (branch
    `refs/convert/parquet`, pinned by its own sha) so that only the first 20,000 rows need fetching.
    The `SYSTEM:` text is not kept as a message: its function list becomes `tools` (OpenAI shape)
    and the template writes its own tools preamble. Each `<functioncall>` becomes a `tool_calls`
    entry with an id and each `FUNCTION RESPONSE` a `tool` message. Rows with no functions, with
    functions but no call, or that do not parse cleanly (about 7% of those with a call) are skipped.
16. OpenThoughts is read from its `metadata` config (separate problem, reasoning and solution
    columns) rather than the default config, whose assistant text wraps both in its own markers and
    whose system prompt describes that format. No system message is used. The puzzle rows are not
    used; science is the biology, physics and chemistry rows.
17. Wikipedia rows are the title, a blank line and the text. Only row groups 0 and 40 of each
    language's first shard are read (2,000 articles), which leans towards older, longer articles.
18. Row groups are fetched with HTTP range requests instead of downloading whole shards; the cache
    holds only those row groups and columns.

Both sets

19. Extra fields. `source_row` is the first source row and `source_rows` lists all of them (they
    differ only for math). Rows also carry `window`, `truncated`, `reasoning_effort`, `domain` and
    `licence` where they apply.
20. Disjointness is by construction: in every source that feeds both sets, rows whose index in the
    file is a multiple of 5 can only go to evaluation and all other rows only to calibration (math
    uses the test and train splits instead). No source row is used twice.
21. Any source text containing one of the tokenizer's 36 added-token strings (`<think>`, `[MASK]`,
    `<|user|>`, `/nothink`, ...) is skipped, so plain documents hold no control ids after the
    prefix and chat rows hold only the ones the template wrote.
22. Nothing is appended at the end of a document or conversation: no `<|endoftext|>`, no trailing
    role token, no generation prompt. A cut never ends inside a character: trailing tokens that
    would leave half a UTF-8 character are dropped, so a cut row can be up to three tokens short of
    the limit.
23. `<think>`, `</think>`, `<tool_call>`, `<arg_key>`, `<tool_response>` and their closing forms are
    single ids, but tokenizer.json marks them `special: false` (only `<|endoftext|>` to
    `<|end_of_transcription|>`, ids 154820 to 154837, are `special: true`). Decoding with
    `skip_special_tokens=True` keeps them.

Template rendering

24. The template is rendered with jinja2 set up as transformers does it: an
    `ImmutableSandboxedEnvironment` with `trim_blocks`, `lstrip_blocks`, the `loopcontrols`
    extension (the template uses `break`), transformers' `tojson` (plain `json.dumps`, no HTML
    escaping, `ensure_ascii=False`), `raise_exception` and `strftime_now`; called with `messages`,
    `tools`, `documents=None`, `add_generation_prompt=False`, `eos_token`, `pad_token` and
    `reasoning_effort` when set; tokenized with `add_special_tokens=False`. `test_sets.py` compares
    this with `PreTrainedTokenizerFast.apply_chat_template` on four fixed cases and on every chat
    row saved in `cache/render_samples.jsonl` (all 64 evaluation chat rows and 40 calibration rows
    per chat category).
25. Not checked: the model repo also ships `tokenization_glm5.py` (the `Glm5Tokenizer` named in
    `auto_map`), `processing_glm5.py` and a vLLM patch about tool and media ordering. They were not
    downloaded, read or run. The cross-check above uses the stock fast tokenizer class with the
    shipped `tokenizer.json` and `chat_template.jinja`; if the custom class changes how text is
    encoded or how the template is applied, these sets would not show it.
"""


def _write_jsonl(path, rows):
    with path.open("w") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False, separators=(",", ":")) + "\n")
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _ranges(indices):
    """Compact '1-3, 7, 9-12' form of a list of ints."""
    out, indices = [], sorted(indices)
    i = 0
    while i < len(indices):
        j = i
        while j + 1 < len(indices) and indices[j + 1] == indices[j] + 1:
            j += 1
        out.append(str(indices[i]) if i == j else f"{indices[i]}-{indices[j]}")
        i = j + 1
    return ", ".join(out)


def _table(rows, by):
    stats = collections.OrderedDict()
    for r in rows:
        s = stats.setdefault(by(r), [0, 0, 10**9, 0])
        s[0] += 1
        s[1] += r["n_tokens"]
        s[2] = min(s[2], r["n_tokens"])
        s[3] = max(s[3], r["n_tokens"])
    return stats


def write_manifest(eval_rows, calib_rows, hashes):
    used = {"eval": collections.defaultdict(list), "calib": collections.defaultdict(list)}
    for name, rows in (("eval", eval_rows), ("calib", calib_rows)):
        for r in rows:
            used[name][r["source"]].extend(r["source_rows"])
    rows_used = {
        name: {src: sorted(idx) for src, idx in sorted(per.items())} for name, per in used.items()
    }
    (DATA / "rows_used.json").write_text(json.dumps(rows_used, indent=1) + "\n")

    L = []
    L.append("# DaisyRose-27B calibration and evaluation token sets")
    L.append("")
    L.append(f"Model `{MODEL_REPO}` at revision `{MODEL_REV}`. Seed {SEED}. Written by `build_sets.py`; do not edit by hand.")
    L.append("")
    L.append("| file | rows | tokens | sha256 |")
    L.append("|---|---:|---:|---|")
    for name, rows in (("eval.jsonl", eval_rows), ("calib.jsonl", calib_rows)):
        L.append(f"| `{name}` | {len(rows)} | {sum(r['n_tokens'] for r in rows):,} | sha256 `{hashes[name]}` |")
    L.append("")
    import jinja2
    import pyarrow
    import tokenizers

    L.append(f"Built with Python {sys.version.split()[0]}, tokenizers {tokenizers.__version__}, "
             f"jinja2 {jinja2.__version__}, pyarrow {pyarrow.__version__}.")
    L.append("")
    L.append("Tokenizer and template files (in `cache/model/`):")
    L.append("")
    for name in MODEL_FILES:
        L.append(f"- `{name}` sha256 `{hashlib.sha256((MODEL_DIR / name).read_bytes()).hexdigest()}`")
    L.append("")

    L.append("## Evaluation set")
    L.append("")
    L.append("| category | documents | tokens | shortest | longest |")
    L.append("|---|---:|---:|---:|---:|")
    for cat, (n, t, lo, hi) in _table(eval_rows, lambda r: r["category"]).items():
        L.append(f"| {cat} | {n} | {t:,} | {lo} | {hi} |")
    L.append(f"| **total** | {len(eval_rows)} | {sum(r['n_tokens'] for r in eval_rows):,} | | |")
    L.append("")

    def reasoning_kind(r):
        if r["truncated"] == "none":
            kind = "whole conversation"
        elif THINK_END in r["input_ids"]:
            kind = "cut inside the answer"
        else:
            kind = "cut inside the reasoning"
        return f"{r['domain']}, {kind}"

    L.append("Reasoning chat by question domain and cut:")
    L.append("")
    L.append("| | documents | tokens |")
    L.append("|---|---:|---:|")
    kinds = _table(sorted((r for r in eval_rows if r["category"] == "chat_reasoning"), key=reasoning_kind),
                   reasoning_kind)
    for k, (n, t, _, _) in kinds.items():
        L.append(f"| {k} | {n} | {t:,} |")
    L.append("")

    total = sum(r["n_tokens"] for r in calib_rows)
    L.append("## Calibration set")
    L.append("")
    L.append("| group | target | share | category | sequences | tokens | shortest | longest |")
    L.append("|---|---:|---:|---|---:|---:|---:|---:|")
    table = _table(calib_rows, lambda r: r["category"])
    for group, target in CALIB_TARGETS.items():
        share = 100 * sum(table[c][1] for c in group) / total
        for i, cat in enumerate(group):
            n, t, lo, hi = table[cat]
            head = f"| {' + '.join(group)} | {target}% | {share:.1f}% |" if i == 0 else "| | | |"
            L.append(f"{head} {cat} | {n} | {t:,} | {lo} | {hi} |")
    L.append(f"| **total** | 100% | 100% | | {len(calib_rows)} | {total:,} | | |")
    L.append("")

    def sub(title, rows, by):
        L.append(f"{title}:")
        L.append("")
        L.append("| | sequences | tokens |")
        L.append("|---|---:|---:|")
        for k, (n, t, _, _) in _table(rows, by).items():
            L.append(f"| {k} | {n} | {t:,} |")
        L.append("")

    sub("Reasoning chat by question domain and cut",
        sorted((r for r in calib_rows if r["category"] == "chat_reasoning"), key=reasoning_kind),
        reasoning_kind)
    sub("Chat rows by `reasoning_effort` passed to the template (none = the template's default, Max)",
        [r for r in calib_rows if "reasoning_effort" in r],
        lambda r: f"{r['category']}, {r['reasoning_effort'] or 'none'}")
    sub("Plain multi-turn chat by cut",
        [r for r in calib_rows if r["category"] == "chat"],
        lambda r: "whole conversation" if r["truncated"] == "none" else "trailing exchanges dropped to fit")
    sub("Code by language", [r for r in calib_rows if r["category"] == "code"], lambda r: r["lang"])
    sub("Other languages", [r for r in calib_rows if r["category"] == "prose_multilingual"], lambda r: r["lang"])
    sub("Science by source", [r for r in calib_rows if r["category"] == "science"],
        lambda r: r["source"].split("@")[0])
    sub("Plain documents by window (whole = shorter than the window, head = first 2,048 tokens, "
        "offset = 2,048 tokens from a random line)",
        [r for r in calib_rows if "window" in r], lambda r: r["window"])

    L.append("## Sources")
    L.append("")
    L.append("All fetched anonymously over HTTPS from `https://huggingface.co/datasets/<id>/resolve/<revision>/<file>`. "
             "Row indices are 0-based positions in the named file. The complete index lists are in `rows_used.json`; "
             "each JSONL row also carries its own `source` and `source_rows`.")
    L.append("")
    for key, src in SOURCES.items():
        L.append(f"### {src['dataset']}")
        L.append("")
        L.append(f"- revision `{src['revision']}`" + (f" ({src['note']})" if "note" in src else ""))
        L.append(f"- licence: {src['licence']}")
        files = sorted({s for name in used for s in used[name] if s.startswith(src["dataset"] + "@")})
        for sid in files:
            path = sid.split(":", 1)[1]
            for name in ("eval", "calib"):
                idx = used[name].get(sid)
                if idx:
                    text = _ranges(idx)
                    if len(text) > 400:
                        text = f"{len(idx)} rows between {min(idx)} and {max(idx)} (list in `rows_used.json`)"
                    L.append(f"- `{path}` {name}: {text}")
        if key in ("code", "arxiv", "pubmed"):
            lic = collections.Counter(
                r["licence"] for r in eval_rows + calib_rows if r["source"].startswith(src["dataset"] + "@")
            )
            L.append("- per-row licences used: " + "; ".join(f"{k} ({v})" for k, v in lic.most_common()))
        L.append("")

    L.append("## Row format")
    L.append("")
    L.append(ROW_FORMAT)
    L.append("## Deviations from the brief and things to know")
    L.append("")
    L.append(DEVIATIONS)
    (DATA / "MANIFEST.md").write_text("\n".join(L))


ROW_FORMAT = """\
One JSON object per line:

- `id`: `eval-<category>-NNN` or `calib-<category>-NNNN`
- `category`: evaluation has `code`, `prose_en`, `prose_ja`, `math`, `science`, `chat_reasoning`,
  `tool_calling`; calibration has `chat_reasoning`, `chat`, `tool_calling`, `code`, `prose_en`,
  `science`, `prose_multilingual`, `math`
- `lang`: language code of the text (`en`, `ja`, ...); for `code` the programming language
- `source`: `<dataset id>@<revision sha>:<file>`
- `source_row`: 0-based index of the (first) source row in that file; `source_rows`: all of them
- `n_tokens`, `input_ids`: the sequence, with no prefix token (Qwen adds no BOS)
- `window` (plain documents): `whole`, `head` or `offset`
- `truncated` (chat rows): `none`, `turns` or `tokens`
- `reasoning_effort` (chat rows): `null` (xhigh), `"medium"` or `"low"` as passed to the template
- `domain` (reasoning chat): `code`, `math` or `science`
- `licence` (code and science): the licence the source gives for that row
"""


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.parse_args()
    tok = load_tokenizer()
    used, samples = Used(), []
    print("evaluation set", file=sys.stderr)
    eval_rows = build_eval(tok, used, samples)
    print("calibration set", file=sys.stderr)
    calib_rows = build_calib(tok, used, samples)
    hashes = {
        "eval.jsonl": _write_jsonl(DATA / "eval.jsonl", eval_rows),
        "calib.jsonl": _write_jsonl(DATA / "calib.jsonl", calib_rows),
    }
    _write_jsonl(CACHE / "render_samples.jsonl", samples)
    write_manifest(eval_rows, calib_rows, hashes)
    total = sum(r["n_tokens"] for r in calib_rows)
    print(f"eval: {len(eval_rows)} rows, {sum(r['n_tokens'] for r in eval_rows):,} tokens", file=sys.stderr)
    print(f"calib: {len(calib_rows)} rows, {total:,} tokens", file=sys.stderr)
    for name, digest in hashes.items():
        print(f"{name} sha256 {digest}", file=sys.stderr)


if __name__ == "__main__":
    main()
