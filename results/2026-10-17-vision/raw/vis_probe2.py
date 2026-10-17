#!/usr/bin/env python3
# SPDX-License-Identifier: AGPL-3.0-only
"""vis_probe2.py TAG CASES... : second-window checks for the sparkqwen#10 fix (127.0.0.1:8893). Reuses vis_rows_probe.

Cases:
  seq       a5 -> b16680 -> d8 in that order (the cached-skip sequence), every label checked
  labels    8 distinct images cold-ish (fresh salt via a leading text line), then the same request again warm
  blocking  non-stream chat / responses / messages: 2 concurrent 2x2048^2 requests (8192 rows each) both admitted,
            then 3 concurrent: at most 2 admitted (needs --vision-max-inflight-rows 16384)
  atomic    8 parallel 8x2048^2 (32768 rows each) at the default budget: <=2 admitted, rest 503 + Retry-After;
            after idle a full request is admitted again
  hostile2  50 header-only 8000^2 PNGs (expect 400 vision_input_too_large fast); one 16384^2 RGBA16 header (expect 400)
  rotated   a 6000x4000 JPEG with EXIF Orientation=6 (displayed portrait) showing a red triangle: expect 200 + 'red triangle'
  big       one 12000x9000 RGB photo-sized PNG (324 MB decoded, over the large-decode gate, under the 640 MiB limit): expect 200
  exact     single 1024^2, 1920x1080, 1337x5293 images and 3 x 1024^2, greedy: texts saved for an old/new byte comparison
"""
import base64, concurrent.futures as cf, io, json, sys, time
sys.path.insert(0, __import__("os").path.dirname(__file__))
import vis_rows_probe as P
from PIL import Image, ImageDraw


def png_rgba16_header(w, h):
    import struct, zlib
    def chunk(t, d):
        return struct.pack(">I", len(d)) + t + d + struct.pack(">I", zlib.crc32(t + d) & 0xffffffff)
    return base64.b64encode(b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 16, 6, 0, 0, 0)) + chunk(b"IEND", b"")).decode()


def rotated_jpeg():
    # Stored landscape 6000x4000; Orientation=6 (rotate 90 CW to display) -> displayed 4000x6000 portrait.
    # Draw the triangle so that it points UP in the displayed image: in stored coordinates "up" is "left".
    w, h = 6000, 4000
    im = Image.new("RGB", (w, h), "white"); d = ImageDraw.Draw(im)
    d.polygon([(w * 0.2, h / 2), (w * 0.8, h * 0.2), (w * 0.8, h * 0.8)], fill=(220, 30, 30))
    ex = Image.Exif(); ex[274] = 6
    buf = io.BytesIO(); im.save(buf, "JPEG", quality=85, exif=ex.tobytes())
    return base64.b64encode(buf.getvalue()).decode()


def chat_raw(content, stream=False):
    return {"model": P.MODEL, "messages": [{"role": "user", "content": content}], "max_tokens": 200, "temperature": 0,
            "stream": stream, "chat_template_kwargs": {"enable_thinking": False}}


def img_part(b, mime="png"):
    return {"type": "image_url", "image_url": {"url": f"data:image/{mime};base64,{b}"}}


def main():
    tag, cases = sys.argv[1], sys.argv[2:]
    res = []
    if "seq" in cases:
        for name, imgs in (("a5", P.images(5)), ("b16680", P.images(5, small_last=True)), ("d8", P.images(8))):
            res.append(P.served(tag, f"seq-{name}", imgs))
    if "labels" in cases:
        im8 = P.images(8)
        for k in ("cold", "warm"):
            st, raw, dt = P.post("/v1/chat/completions", P.chat_body(im8, preamble=f"Request {tag}."))
            txt = P.text_of(raw, False) if st == 200 else raw[:300]
            ok = st == 200 and P.in_order(txt, im8)
            print(f"labels {k}: HTTP {st} {dt:.1f}s order_ok={ok} :: {txt[:200]!r}", flush=True)
            res.append({"case": f"labels-{k}", "status": st, "secs": round(dt, 2), "order_ok": ok, "text": txt[:600]})
    if "blocking" in cases:
        im2 = P.images(2)
        bodies = {
            "chat": ("/v1/chat/completions", P.chat_body(im2)),
            "responses": ("/v1/responses", {"model": P.MODEL, "max_output_tokens": 100, "input": [{"role": "user", "content":
                          [{"type": "input_image", "image_url": f"data:image/png;base64,{x}"} for _, _, x in im2] + [{"type": "input_text", "text": P.ASK}]}]}),
            "messages": ("/v1/messages", {"model": P.MODEL, "max_tokens": 100, "messages": [{"role": "user", "content":
                         [{"type": "image", "source": {"type": "base64", "media_type": "image/png", "data": x}} for _, _, x in im2] + [{"type": "text", "text": P.ASK}]}]}),
        }
        for name, (path, body) in bodies.items():
            for n in (2, 3):
                with cf.ThreadPoolExecutor(n) as ex:
                    outs = list(ex.map(lambda i: P.post_h(path, body), range(n)))
                print(f"blocking {name} x{n}: statuses {sorted(o[0] for o in outs)} secs {[round(o[2], 1) for o in outs]}", flush=True)
                res.append({"case": f"blocking-{name}-x{n}", "statuses": [o[0] for o in outs], "secs": [round(o[2], 1) for o in outs]})
                time.sleep(2)
    if "atomic" in cases:
        im8 = P.images(8)
        with cf.ThreadPoolExecutor(8) as ex:
            outs = list(ex.map(lambda i: P.post_h("/v1/chat/completions", P.chat_body(im8, preamble=f"Atomic {i}.")), range(8)))
        busy = [o for o in outs if o[0] in (429, 503)]
        print(f"atomic x8: statuses {sorted(o[0] for o in outs)} retry-after {sorted(set(o[3] for o in busy))} :: {busy[0][1][:200] if busy else ''!r}", flush=True)
        time.sleep(3)
        st, raw, dt, _ = P.post_h("/v1/chat/completions", P.chat_body(im8, preamble="Atomic after idle."))
        print(f"atomic after idle: HTTP {st} {dt:.1f}s", flush=True)
        res.append({"case": "atomic", "statuses": [o[0] for o in outs], "retry_after": [o[3] for o in busy], "after_idle": st})
    if "hostile2" in cases:
        b = P.ihdr_png(8000, 8000)
        body = chat_raw([img_part(b) for _ in range(50)] + [{"type": "text", "text": "hi"}])
        st, raw, dt, _ = P.post_h("/v1/chat/completions", body)
        print(f"hostile 50x8000^2: HTTP {st} {dt*1000:.0f} ms :: {raw[:220]!r}", flush=True)
        st2, raw2, dt2, _ = P.post_h("/v1/chat/completions", chat_raw([img_part(png_rgba16_header(16384, 16384)), {"type": "text", "text": "hi"}]))
        print(f"hostile 16384^2 RGBA16: HTTP {st2} {dt2*1000:.0f} ms :: {raw2[:220]!r}", flush=True)
        res.append({"case": "hostile2", "many": [st, round(dt, 3), raw[:300]], "rgba16": [st2, round(dt2, 3), raw2[:300]]})
    if "rotated" in cases:
        st, raw, dt = P.post("/v1/chat/completions", chat_raw([img_part(rotated_jpeg(), "jpeg"),
                             {"type": "text", "text": "What colour and shape is shown, and which way does it point (up, down, left or right)?"}]))
        txt = P.text_of(raw, False) if st == 200 else raw[:300]
        print(f"rotated 6000x4000 EXIF=6: HTTP {st} {dt:.1f}s :: {txt[:200]!r}", flush=True)
        res.append({"case": "rotated", "status": st, "secs": round(dt, 2), "text": txt[:400]})
    if "big" in cases:
        st, raw, dt = P.post("/v1/chat/completions", P.chat_body([("red", "circle", P.png("red", "circle", 12000, 9000))]))
        txt = P.text_of(raw, False) if st == 200 else raw[:300]
        print(f"big 12000x9000: HTTP {st} {dt:.1f}s :: {txt[:160]!r}", flush=True)
        res.append({"case": "big", "status": st, "secs": round(dt, 2), "text": txt[:400]})
    if "bigx8" in cases:
        bigs = [P.png(c, sh, 12000, 9000) for c, sh in P.SHAPES[:8]]
        m0, lo, stop = P.mem("01"), [P.mem("01")], [False]
        import threading
        def watch():
            while not stop[0]:
                lo.append(P.mem("01")); time.sleep(0.2)
        th = threading.Thread(target=watch); th.start()
        with cf.ThreadPoolExecutor(8) as ex:
            outs = list(ex.map(lambda i: P.post_h("/v1/chat/completions", P.chat_body([(P.SHAPES[i][0], P.SHAPES[i][1], bigs[i])])), range(8)))
        stop[0] = True; th.join()
        print(f"bigx8 12000x9000: statuses {sorted(o[0] for o in outs)} secs {[round(o[2], 1) for o in outs]} rank0 host MemAvailable dip {(m0 - min(lo)) / 1024:.2f} GiB", flush=True)
        res.append({"case": "bigx8", "statuses": [o[0] for o in outs], "mem_dip_gib": round((m0 - min(lo)) / 1024, 2)})
    if "exact" in cases:
        out = {}
        for name, (w, h, n) in {"1024sq": (1024, 1024, 1), "1920x1080": (1920, 1080, 1), "1337x5293": (1337, 5293, 1), "3x1024sq": (1024, 1024, 3)}.items():
            imgs = [(c, s, P.png(c, s, w, h)) for c, s in P.SHAPES[:n]]
            st, raw, dt = P.post("/v1/chat/completions", P.chat_body(imgs))
            out[name] = {"status": st, "text": P.text_of(raw, False) if st == 200 else raw[:300]}
            st2, raw2, _ = P.post("/v1/chat/completions", P.chat_body(imgs))   # warm repeat
            out[name + "-warm"] = {"status": st2, "text": P.text_of(raw2, False) if st2 == 200 else raw2[:300]}
            print(f"exact {name}: HTTP {st}/{st2} warm==cold {out[name]['text'] == out[name + '-warm']['text']} :: {out[name]['text'][:100]!r}", flush=True)
        json.dump(out, open(f"exact-{tag}.json", "w"), indent=1)
    json.dump({"tag": tag, "results": res}, open(f"visprobe2-{tag}.json", "w"), indent=1)


if __name__ == "__main__":
    main()
