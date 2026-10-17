#!/usr/bin/env python3
# SPDX-License-Identifier: AGPL-3.0-only
"""vis_rows_probe.py TAG CASES... : multi-image row-cap probe for sparkqwen#10 against 127.0.0.1:8893.

Cases:
  a5       5 x 2048^2 images (20,480 vision rows)
  b16680   4 x 2048^2 + 256 x 1184 (the reporter's 16,680 rows)
  c9       9 x 2048^2 (36,864 rows): expect HTTP 400 (chat non-stream, chat stream, /v1/messages)
  d8       8 x 2048^2 (32,768 rows, the default limit)
  e20k     a ~20K-token text preamble, then 5 x 2048^2 (images straddle prefill chunks)
  mem4     4 concurrent d8 requests while sampling MemAvailable on 01 and 02 every second
  retina   single 2880x1800 and 2064x2032 images, each alone: expect 200 and a correct shape
  hostile  50 header-only PNGs declaring 16000x12000 (~60 B each) in one request, then 8 concurrent copies:
           expect a fast 400 and no MemAvailable dip (sampled every 0.2 s). FIX BINARY ONLY.
  budget   needs a server with --vision-max-inflight-rows 16384: 8 parallel 2 x 2048^2 requests on chat, responses and
           messages: expect 503 + Retry-After for the overflow; then a 16384-row request is admitted (permits returned)
Writes visrows-TAG.json. Each image shows one coloured shape on white; the model is asked to list them in order.
"""
import base64, concurrent.futures as cf, io, json, subprocess, sys, threading, time, urllib.error, urllib.request

from PIL import Image, ImageDraw

URL = "http://127.0.0.1:8893"
MODEL = "qwen3.8-flash-next-atlas"
SHAPES = [("red", "circle"), ("blue", "square"), ("green", "triangle"), ("orange", "circle"), ("purple", "square"),
          ("black", "triangle"), ("yellow", "circle"), ("pink", "square"), ("brown", "triangle")]
RGB = {"red": (220, 30, 30), "blue": (30, 60, 220), "green": (30, 160, 60), "orange": (245, 140, 20), "purple": (130, 40, 170),
       "black": (10, 10, 10), "yellow": (240, 210, 20), "pink": (240, 120, 180), "brown": (130, 80, 30)}


def png(colour, shape, w=2048, h=2048):
    im = Image.new("RGB", (w, h), "white"); d = ImageDraw.Draw(im)
    x0, y0, x1, y1 = w * 0.2, h * 0.2, w * 0.8, h * 0.8
    if shape == "circle":
        d.ellipse((x0, y0, x1, y1), fill=RGB[colour])
    elif shape == "square":
        d.rectangle((x0, y0, x1, y1), fill=RGB[colour])
    else:
        d.polygon([(w / 2, y0), (x1, y1), (x0, y1)], fill=RGB[colour])
    buf = io.BytesIO(); im.save(buf, "PNG")
    return base64.b64encode(buf.getvalue()).decode()


def images(n, small_last=False):
    out = []
    for i in range(n):
        c, s = SHAPES[i]
        w, h = (256, 1184) if (small_last and i == n - 1) else (2048, 2048)
        out.append((c, s, png(c, s, w, h)))
    return out


ASK = "Each image shows one coloured shape. List the shapes in the order the images appear, one per line, as 'colour shape'."


def chat_body(imgs, preamble="", stream=False):
    content = ([{"type": "text", "text": preamble}] if preamble else []) + \
              [{"type": "image_url", "image_url": {"url": f"data:image/png;base64,{b}"}} for _, _, b in imgs] + [{"type": "text", "text": ASK}]
    return {"model": MODEL, "messages": [{"role": "user", "content": content}], "max_tokens": 300, "temperature": 0, "stream": stream,
            "chat_template_kwargs": {"enable_thinking": False}}


def post(path, body, timeout=900):
    req = urllib.request.Request(URL + path, json.dumps(body).encode(), {"Content-Type": "application/json", "anthropic-version": "2023-06-01"})
    t = time.time()
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            raw = r.read().decode(errors="replace"); return r.status, raw, time.time() - t
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode(errors="replace"), time.time() - t
    except Exception as e:  # connection reset, timeout
        return -1, f"{type(e).__name__}: {e}", time.time() - t


def text_of(raw, stream):
    if stream:
        parts = []
        for line in raw.splitlines():
            if line.startswith("data: ") and line[6:].strip() not in ("", "[DONE]"):
                try:
                    d = json.loads(line[6:]); parts.append(d["choices"][0]["delta"].get("content") or "")
                except Exception:
                    parts.append(line[6:200])
        return "".join(parts)
    try:
        return json.loads(raw)["choices"][0]["message"]["content"] or ""
    except Exception:
        return raw[:400]


def in_order(text, imgs):
    t = text.lower(); pos = 0
    for c, s, _ in imgs:
        i = t.find(c, pos)
        if i < 0 or s not in t[i:i + 40]:
            return False
        pos = i + len(c)
    return True


def served(tag, name, imgs, preamble=""):
    st, raw, dt = post("/v1/chat/completions", chat_body(imgs, preamble))
    txt = text_of(raw, False) if st == 200 else raw[:400]
    ok = st == 200 and in_order(txt, imgs)
    print(f"{name}: HTTP {st} {dt:.1f}s order_ok={ok} :: {txt[:160]!r}", flush=True)
    return {"case": name, "status": st, "secs": round(dt, 2), "order_ok": ok, "text": txt[:600]}


def ihdr_png(w, h):
    import struct, zlib
    def chunk(t, d):
        return struct.pack(">I", len(d)) + t + d + struct.pack(">I", zlib.crc32(t + d) & 0xffffffff)
    return base64.b64encode(b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 2, 0, 0, 0)) + chunk(b"IEND", b"")).decode()


def post_h(path, body, timeout=900):
    req = urllib.request.Request(URL + path, json.dumps(body).encode(), {"Content-Type": "application/json", "anthropic-version": "2023-06-01"})
    t = time.time()
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status, r.read().decode(errors="replace"), time.time() - t, r.headers.get("Retry-After")
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode(errors="replace"), time.time() - t, e.headers.get("Retry-After")
    except Exception as e:
        return -1, f"{type(e).__name__}: {e}", time.time() - t, None


def mem(host):
    cmd = ["awk", "/MemAvailable/{print int($2/1024)}", "/proc/meminfo"]
    if host != "01":
        cmd = ["ssh", "-n", "rank1-host", " ".join(["awk", "'/MemAvailable/{print int($2/1024)}'", "/proc/meminfo"])]
    return int(subprocess.run(cmd, capture_output=True, text=True).stdout.strip() or -1)


def main():
    tag, cases = sys.argv[1], sys.argv[2:]
    res = []
    if "a5" in cases: res.append(served(tag, "a5", images(5)))
    if "b16680" in cases: res.append(served(tag, "b16680", images(5, small_last=True)))
    if "d8" in cases: res.append(served(tag, "d8", images(8)))
    if "e20k" in cases:
        pre = " ".join(f"Note {i}: the archive shelf holds ledger {i} beside crate {i * 7}." for i in range(1500))
        res.append(served(tag, "e20k", images(5), preamble=pre))
    if "c9" in cases:
        im9 = images(9)
        for name, path, body in (("c9-chat", "/v1/chat/completions", chat_body(im9)),
                                 ("c9-chat-stream", "/v1/chat/completions", chat_body(im9, stream=True)),
                                 ("c9-messages", "/v1/messages", {"model": MODEL, "max_tokens": 300, "messages": [{"role": "user", "content":
                                     [{"type": "image", "source": {"type": "base64", "media_type": "image/png", "data": b}} for _, _, b in im9] +
                                     [{"type": "text", "text": ASK}]}]})):
            st, raw, dt = post(path, body)
            print(f"{name}: HTTP {st} {dt:.1f}s :: {raw[:300]!r}", flush=True)
            res.append({"case": name, "status": st, "secs": round(dt, 2), "body": raw[:600]})
    if "mem4" in cases:
        im8 = images(8); samples = []; stop = threading.Event()
        base = {"01": mem("01"), "02": mem("02")}

        def sampler():
            while not stop.is_set():
                samples.append((round(time.time(), 1), mem("01"), mem("02"))); time.sleep(1)
        th = threading.Thread(target=sampler, daemon=True); th.start()
        with cf.ThreadPoolExecutor(4) as ex:
            outs = list(ex.map(lambda i: post("/v1/chat/completions", chat_body(im8)), range(4)))
        stop.set(); th.join()
        lo1, lo2 = min(s[1] for s in samples), min(s[2] for s in samples)
        print(f"mem4: statuses {[o[0] for o in outs]} secs {[round(o[2], 1) for o in outs]} MemAvailable MiB before 01={base['01']} 02={base['02']} min 01={lo1} 02={lo2}", flush=True)
        res.append({"case": "mem4", "statuses": [o[0] for o in outs], "secs": [round(o[2], 1) for o in outs], "mem_before": base,
                    "mem_min": {"01": lo1, "02": lo2}, "samples": samples,
                    "order_ok": [in_order(text_of(o[1], False), im8) if o[0] == 200 else False for o in outs]})
    if "retina" in cases:
        for (w, h), (c, sh) in (((2880, 1800), ("red", "circle")), ((2064, 2032), ("blue", "square"))):
            im = [(c, sh, png(c, sh, w, h))]
            st, raw, dt = post("/v1/chat/completions", chat_body(im))
            txt = text_of(raw, False) if st == 200 else raw[:300]
            try:
                vt = json.loads(raw)["usage"].get("prompt_tokens")
            except Exception:
                vt = None
            ok = st == 200 and in_order(txt, im)
            print(f"retina {w}x{h}: HTTP {st} {dt:.1f}s prompt_tokens={vt} ok={ok} :: {txt[:120]!r}", flush=True)
            res.append({"case": f"retina-{w}x{h}", "status": st, "secs": round(dt, 2), "ok": ok, "prompt_tokens": vt, "text": txt[:300]})
    if "hostile" in cases:
        b = ihdr_png(16000, 12000)
        body = {"model": MODEL, "max_tokens": 16, "messages": [{"role": "user", "content":
                [{"type": "image_url", "image_url": {"url": f"data:image/png;base64,{b}"}} for _ in range(50)] + [{"type": "text", "text": "hi"}]}]}
        samples = []; stop = threading.Event(); base = mem("01")

        def sampler():
            while not stop.is_set():
                samples.append(mem("01")); time.sleep(0.2)
        th = threading.Thread(target=sampler, daemon=True); th.start(); time.sleep(0.5)
        one = post_h("/v1/chat/completions", body)
        with cf.ThreadPoolExecutor(8) as ex:
            many = list(ex.map(lambda i: post_h("/v1/chat/completions", body), range(8)))
        time.sleep(0.5); stop.set(); th.join()
        print(f"hostile: single HTTP {one[0]} {one[2]*1000:.0f} ms :: {one[1][:200]!r}", flush=True)
        print(f"hostile x8: statuses {[m[0] for m in many]} max {max(m[2] for m in many)*1000:.0f} ms; rank0 MemAvailable MiB before {base} min {min(samples)}", flush=True)
        res.append({"case": "hostile", "single": [one[0], round(one[2], 3), one[1][:300]], "x8": [[m[0], round(m[2], 3)] for m in many],
                    "mem_before": base, "mem_min": min(samples)})
    if "budget" in cases:
        im2 = images(2)
        chat = chat_body(im2)
        resp = {"model": MODEL, "max_output_tokens": 100, "input": [{"role": "user", "content":
                [{"type": "input_image", "image_url": f"data:image/png;base64,{x}"} for _, _, x in im2] + [{"type": "input_text", "text": ASK}]}]}
        msgs = {"model": MODEL, "max_tokens": 100, "messages": [{"role": "user", "content":
                [{"type": "image", "source": {"type": "base64", "media_type": "image/png", "data": x}} for _, _, x in im2] + [{"type": "text", "text": ASK}]}]}
        for name, path, body in (("chat", "/v1/chat/completions", chat), ("responses", "/v1/responses", resp), ("messages", "/v1/messages", msgs)):
            with cf.ThreadPoolExecutor(8) as ex:
                outs = list(ex.map(lambda i: post_h(path, body), range(8)))
            busy = [o for o in outs if o[0] in (429, 503)]
            print(f"budget {name}: statuses {sorted(o[0] for o in outs)} retry-after {sorted(set(o[3] for o in busy))} sample busy body {busy[0][1][:220] if busy else ''!r}", flush=True)
            res.append({"case": f"budget-{name}", "statuses": [o[0] for o in outs], "retry_after": [o[3] for o in busy], "busy_body": busy[0][1][:400] if busy else ""})
        time.sleep(3)
        st, raw, dt, _ = post_h("/v1/chat/completions", chat_body(images(4)))
        print(f"budget after idle: 4 x 2048^2 (16384 rows) HTTP {st} {dt:.1f}s", flush=True)
        res.append({"case": "budget-after-idle", "status": st, "secs": round(dt, 2)})
    json.dump({"tag": tag, "results": res}, open(f"visrows-{tag}.json", "w"), indent=1)


if __name__ == "__main__":
    main()
