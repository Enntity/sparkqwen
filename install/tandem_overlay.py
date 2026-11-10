#!/usr/bin/env python3
# SPDX-License-Identifier: AGPL-3.0-only
"""Build the 27B checkpoint overlay: NVIDIA's Qwen3.8-27B-NVFP4 with its Gated
DeltaNet and attention projections replaced by TandemLLM's NVFP4 weights.

  tandem_overlay.py PIN CHECKPOINT_DIR WEIGHTS_DIR OVERLAY_DIR

PIN is install/checkpoint-27b.json; its "overlay" entry names the files, their
sha256 and the source revision. Every file in WEIGHTS_DIR is checked against it
first. The weights are in the ModelOpt NVFP4 layout already (E2M1 codes low
nibble first, an E4M3 scale per 16 inputs in a plain [N, K/16] grid, one F32
weight_scale_2 per tensor) under `layers.N.<module>.<proj>` names. This script
copies their bytes under the checkpoint's `model.language_model.layers.N...`
names, with one change Atlas requires: it concatenates a GDN layer's in_proj_qkv
and in_proj_z into one projection with a single weight_scale_2, so in_proj_z's
E4M3 block scales are re-expressed against in_proj_qkv's (scale * s2_z / s2_qkv
in float32, clamped to 448, rounded to the nearest E4M3); its codes and every
other byte are unchanged. The overlay directory links NVIDIA's files and gets a
rewritten index and hf_quant_config.json; it must sit next to CHECKPOINT_DIR.
Standard library only."""
import bisect
import hashlib
import json
import os
import struct
import sys

PRE = 'model.language_model.layers.'
CHUNK = 1 << 26


def f32(x):
    return struct.unpack('<f', struct.pack('<f', x))[0]


def e4m3(code):
    """E4M3 (fn) byte -> float; 0x7F / 0xFF are NaN."""
    s, e, m = code >> 7, (code >> 3) & 15, code & 7
    if e == 15 and m == 7:
        return float('nan')
    v = (m / 8) * 2.0 ** -6 if e == 0 else (1 + m / 8) * 2.0 ** (e - 7)
    return -v if s else v


POS = [e4m3(c) for c in range(0x7F)]  # 0 .. 448, ascending


def to_e4m3(v):
    """Positive float -> nearest E4M3 code, ties to even, saturating at 448."""
    if v != v or v <= 0:
        return 0
    if v >= POS[-1]:
        return 0x7E
    i = bisect.bisect_left(POS, v)
    if POS[i] == v:
        return i
    lo, hi = i - 1, i
    dl, dh = v - POS[lo], POS[hi] - v
    return lo if dl < dh or (dl == dh and lo % 2 == 0) else hi


def rescale_table(ratio):
    """bytes.translate table for scale -> scale * ratio, as float32."""
    r = f32(ratio)
    out = bytearray(256)
    for c in range(256):
        v = e4m3(c)
        out[c] = 0x7F if v != v else to_e4m3(min(f32(f32(abs(v)) * r), 448.0)) | (c & 0x80)
    return bytes(out)


def header(path):
    with open(path, 'rb') as f:
        n = struct.unpack('<Q', f.read(8))[0]
        meta = json.loads(f.read(n))
    return meta, 8 + n


def sha256(path):
    h = hashlib.sha256()
    with open(path, 'rb') as f:
        while block := f.read(CHUNK):
            h.update(block)
    return h.hexdigest()


def rekey(src, dst):
    """Copy src under checkpoint names; returns the tensor names written."""
    meta, start = header(src)
    info = {k: v for k, v in meta.items() if k != '__metadata__'}
    names = {k: PRE + k[len('layers.'):] for k in info}
    with open(src, 'rb') as f:
        def raw(k):
            a, b = info[k]['data_offsets']
            f.seek(start + a)
            return f.read(b - a)
        patch = {}
        for k in info:
            if k.endswith('.in_proj_z.weight_scale'):
                base = k[:-len('in_proj_z.weight_scale')]
                s2q = struct.unpack('<f', raw(base + 'in_proj_qkv.weight_scale_2'))[0]
                s2z = struct.unpack('<f', raw(base + 'in_proj_z.weight_scale_2'))[0]
                if s2q != s2z:
                    patch[k] = raw(k).translate(rescale_table(s2z / s2q))
                    patch[base + 'in_proj_z.weight_scale_2'] = struct.pack('<f', s2q)
        out, offset, order = {}, 0, sorted(info)
        for k in order:
            a, b = info[k]['data_offsets']
            out[names[k]] = {'dtype': info[k]['dtype'], 'shape': info[k]['shape'], 'data_offsets': [offset, offset + b - a]}
            offset += b - a
        out['__metadata__'] = {'source': os.path.basename(src), 'rekeyed_by': 'sparkqwen install/tandem_overlay.py'}
        blob = json.dumps(out, separators=(',', ':')).encode()
        blob += b' ' * (-len(blob) % 8)
        with open(dst + '.tmp', 'wb') as g:
            g.write(struct.pack('<Q', len(blob)) + blob)
            for k in order:
                if k in patch:
                    g.write(patch[k])
                    continue
                a, b = info[k]['data_offsets']
                f.seek(start + a)
                left = b - a
                while left:
                    block = f.read(min(CHUNK, left))
                    g.write(block)
                    left -= len(block)
    os.replace(dst + '.tmp', dst)
    return [names[k] for k in order]


def build(pin, checkpoint, weights, overlay):
    spec = json.load(open(pin))['overlay']
    for name, digest in spec['files'].items():
        got = sha256(os.path.join(weights, name))
        if got != digest:
            raise SystemExit(f'{name}: sha256 {got}, pinned {digest}')
    os.makedirs(overlay, exist_ok=True)
    for name in os.listdir(checkpoint):
        link = os.path.join(overlay, name)
        if name not in ('model.safetensors.index.json', 'hf_quant_config.json') and not os.path.lexists(link):
            os.symlink(os.path.relpath(os.path.join(checkpoint, name), overlay), link)
    index = json.load(open(os.path.join(checkpoint, 'model.safetensors.index.json')))
    quant = json.load(open(os.path.join(checkpoint, 'hf_quant_config.json')))
    wm, layers = index['weight_map'], quant['quantization']['quantized_layers']
    for name in spec['serve']:
        dst = 'tandem-' + name
        written = rekey(os.path.join(weights, name), os.path.join(overlay, dst))
        modules = sorted({t.rsplit('.', 1)[0] for t in written})
        for mod in modules:
            for k in [k for k in wm if k.startswith(mod + '.')]:
                del wm[k]
            layers[mod] = {'quant_algo': 'NVFP4', 'group_size': 16}
        for t in written:
            wm[t] = dst
    for name in spec['attribution']:
        with open(os.path.join(weights, name), 'rb') as f, open(os.path.join(overlay, 'TandemLLM-' + name), 'wb') as g:
            g.write(f.read())
    for path, obj in (('model.safetensors.index.json', index), ('hf_quant_config.json', quant)):
        with open(os.path.join(overlay, path + '.tmp'), 'w') as f:
            json.dump(obj, f, indent=2)
        os.replace(os.path.join(overlay, path + '.tmp'), os.path.join(overlay, path))
    with open(os.path.join(overlay, '.sparkqwen-overlay'), 'w') as f:
        f.write(spec['revision'] + '\n')


if __name__ == '__main__':
    if len(sys.argv) != 5:
        sys.exit(__doc__.split('\n\n')[1].strip())
    build(*sys.argv[1:])
