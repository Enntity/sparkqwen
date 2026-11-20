# SPDX-License-Identifier: AGPL-3.0-only
"""Next-token distributions of Qwen3.8-27B checkpoints against the BF16 release,
in one PyTorch forward (transformers' qwen3_5), weights dequantized, activations
BF16 for every arm (what a W4A16 decode step computes).

  kl_eval.py states BF16_DIR EVAL_JSONL OUT.pt [SOURCE ...]
  kl_eval.py compare OUT_DIR TEACHER.pt ARM.pt [ARM.pt ...]

states: loads the BF16 text model, then lays each SOURCE over it in order and
saves what lm_head reads at every position, the lm_head weight the arm uses,
and the document offsets. SOURCE is
  DIR[@REGEX]       every quantized linear stored in the ModelOpt checkpoint DIR
                    (NVFP4 or FP8, read through its index), only modules whose
                    name matches REGEX when given; lm_head too if DIR quantizes it
  tied:DIR[@REGEX]  the same, with each NVFP4 in_proj_z's block scales re-expressed
                    against its layer's in_proj_qkv scale_2 (what Atlas's fused
                    qkvz projection needs; see tie_scale)
  requant@REGEX     re-round the current weights of matching modules to NVFP4
                    (per-16 E4M3 scale = amax/6, F32 scale_2 = amax/(6*448)),
                    what a load-time FP8 -> NVFP4 conversion does
With no SOURCE the arm is the BF16 model itself (the teacher).

compare: KL(BF16 || arm) over the whole vocabulary at every position with a
next token, top-1 agreement and next-token NLL, per category; 95% intervals
resample whole documents; arms after the first are also paired against it.
"""
import json
import os
import random
import re
import sys
import time

import torch
from safetensors import safe_open

DEVICE = os.environ.get('DEVICE', 'cuda')
PREFIX = 'model.language_model.'
E2M1 = torch.tensor([0.0, 0.5, 1.0, 1.5, 2.0, 3.0, 4.0, 6.0,
                     -0.0, -0.5, -1.0, -1.5, -2.0, -3.0, -4.0, -6.0])


def nvfp4_dequant(packed, scale, scale2):
    """ModelOpt NVFP4: uint8 [N, K/2] (even column in the low nibble), E4M3 [N, K/16], F32 scalar."""
    lut = E2M1.to(packed.device)
    v = torch.stack([lut[(packed & 15).long()], lut[(packed >> 4).long()]], -1).flatten(1)
    s = scale.view(torch.float8_e4m3fn).float().repeat_interleave(16, 1)[:, :v.shape[1]]
    return v * s * scale2.float().reshape(())


def fp8_dequant(w, scale):
    """FP8 E4M3 weight with a per-tensor (or per-row) F32 scale."""
    s = scale.float()
    return w.float() * (s.reshape(-1, 1) if s.numel() > 1 else s.reshape(()))


def nvfp4_rtn(w, amax=None):
    """Plain round-to-nearest NVFP4 of a float weight; returns its dequant. amax sets
    scale_2 when the tensor shares it with another (Atlas requantizes a GDN layer's
    in_proj_qkv and in_proj_z as one concatenated [Q|K|V|Z] weight)."""
    w = w.float()
    n, k = w.shape
    amax = (w.abs().max() if amax is None else torch.as_tensor(amax, dtype=torch.float32)).clamp(min=1e-12)
    s2 = amax / (6 * 448)
    g = w.reshape(n, k // 16, 16)
    s = (g.abs().amax(-1) / 6 / s2).clamp(max=448).to(torch.float8_e4m3fn).float()
    q = g / (s * s2).clamp(min=1e-30).unsqueeze(-1)
    ab = E2M1[:8].to(w.device)
    idx = (q.abs().unsqueeze(-1) - ab).abs().argmin(-1)
    return (ab[idx] * q.sign() * (s * s2).unsqueeze(-1)).reshape(n, k)


def tie_scale(scale, s2_from, s2_to):
    """E4M3 block scales re-expressed against another scale_2, as SparkQwen's overlay
    does so Atlas can fuse in_proj_qkv and in_proj_z: scale * s2_from / s2_to in float32,
    clamped to 448, rounded to the nearest E4M3."""
    r = (s2_from.float() / s2_to.float()).reshape(())
    return (scale.view(torch.float8_e4m3fn).float() * r).clamp(max=448).to(torch.float8_e4m3fn)


class Checkpoint:
    def __init__(self, folder, tie_z=False):
        self.tie_z = tie_z
        self.dir = folder
        self.map = json.load(open(os.path.join(folder, 'model.safetensors.index.json')))['weight_map']
        self.files = {}

    def get(self, name):
        shard = self.map.get(name)
        if shard is None:
            return None
        if shard not in self.files:
            self.files[shard] = safe_open(os.path.join(self.dir, shard), 'pt', device=DEVICE)
        return self.files[shard].get_tensor(name)

    def weight(self, full):
        """Dequantized weight of module `full` if this checkpoint quantizes it, else None."""
        w = self.get(full + '.weight')
        if w is None:
            return None
        if w.dtype == torch.uint8:
            s, s2 = self.get(full + '.weight_scale'), self.get(full + '.weight_scale_2')
            if self.tie_z and full.endswith('.in_proj_z'):
                q = self.get(full[:-len('in_proj_z')] + 'in_proj_qkv.weight')
                if q is not None and q.dtype == torch.uint8:
                    s2q = self.get(full[:-len('in_proj_z')] + 'in_proj_qkv.weight_scale_2')
                    s, s2 = tie_scale(s, s2, s2q), s2q
            return nvfp4_dequant(w, s, s2)
        if w.dtype == torch.float8_e4m3fn:
            return fp8_dequant(w, self.get(full + '.weight_scale'))
        return None


def load_text(bf16_dir):
    """The BF16 text model, each tensor read straight to DEVICE (a GB10 cannot stage it twice)."""
    from transformers import Qwen3_5TextConfig, Qwen3_5TextModel
    cfg = Qwen3_5TextConfig(**json.load(open(os.path.join(bf16_dir, 'config.json')))['text_config'])
    with torch.device('meta'):
        text = Qwen3_5TextModel(cfg)
    ck = Checkpoint(bf16_dir)
    for name, t in list(text.named_parameters()) + list(text.named_buffers()):
        owner, _, leaf = name.rpartition('.')
        mod = text.get_submodule(owner)
        v = ck.get(PREFIX + name)
        if v is None:
            continue
        if leaf in mod._parameters:
            mod._parameters[leaf] = torch.nn.Parameter(v, requires_grad=False)
        else:
            mod._buffers[leaf] = v
    with torch.device(DEVICE):
        text.rotary_emb = type(text.rotary_emb)(config=cfg)
    left = [n for n, t in list(text.named_parameters()) + list(text.named_buffers()) if t.is_meta]
    if left:
        raise SystemExit(f'not in the BF16 checkpoint: {left[:8]}')
    text.eval()
    return text, ck.get('lm_head.weight')


def linears(text):
    return [(n, m) for n, m in text.named_modules() if isinstance(m, torch.nn.Linear) and '.layers.' in '.' + n]


def apply(text, lm_head, source):
    """Lay one SOURCE over the model in place; returns (lm_head, {module: kind})."""
    path, _, pattern = source.partition('@')
    rx = re.compile(pattern) if pattern else None
    done = {}
    if path == 'requant':
        mods = dict(linears(text))
        for n, m in mods.items():
            if rx.search(n):
                amax = None
                for a, b in (('in_proj_qkv', 'in_proj_z'), ('in_proj_z', 'in_proj_qkv')):
                    if n.endswith('.' + a) and n[:-len(a)] + b in mods:
                        amax = max(float(m.weight.abs().max()), float(mods[n[:-len(a)] + b].weight.abs().max()))
                done[n] = amax
        for n in done:  # every amax is taken before any weight in the pair changes
            m = mods[n]
            m.weight.data.copy_(nvfp4_rtn(m.weight.data, done[n]).to(m.weight.dtype))
        return lm_head, {n: 'requant' for n in done}
    tied = path.startswith('tied:')
    ck = Checkpoint(path[len('tied:'):] if tied else path, tie_z=tied)
    for n, m in linears(text):
        if rx and not rx.search(n):
            continue
        w = ck.weight(PREFIX + n)
        if w is not None:
            if w.shape != m.weight.shape:
                raise SystemExit(f'{source}: {n} {tuple(w.shape)} != {tuple(m.weight.shape)}')
            m.weight.data.copy_(w.to(m.weight.dtype))
            done[n] = os.path.basename(path.rstrip('/'))
    if not rx or rx.search('lm_head'):
        w = ck.weight('lm_head')
        if w is not None:
            lm_head = w.to(lm_head.dtype)
            done['lm_head'] = os.path.basename(path.rstrip('/'))
    return lm_head, done


@torch.inference_mode()
def states(bf16_dir, eval_jsonl, out, *sources):
    rows = [json.loads(line) for line in open(eval_jsonl)]
    t0 = time.time()
    text, lm_head = load_text(bf16_dir)
    print(f'BF16 loaded in {time.time() - t0:.0f}s', flush=True)
    log = {}
    for s in sources:
        lm_head, done = apply(text, lm_head, s)
        log[s] = len(done)
        print(f'{s}: {len(done)} modules', flush=True)
        if not done:
            raise SystemExit(f'{s}: replaced nothing')
    hs, offsets, t0 = [], [0], time.time()
    for i, r in enumerate(rows):
        h = text(input_ids=torch.tensor([r['input_ids']], device=DEVICE), use_cache=False).last_hidden_state[0]
        hs.append(h.to(torch.bfloat16).cpu())
        offsets.append(offsets[-1] + h.shape[0])
        if i % 32 == 0:
            print(f'  doc {i}: {offsets[-1]:,} tokens, {offsets[-1] / (time.time() - t0):,.0f} tok/s', flush=True)
    torch.save({'hidden': torch.cat(hs), 'offsets': offsets, 'lm_head': lm_head.to(torch.bfloat16).cpu(),
                'sources': list(sources), 'replaced': log, 'ids': [r['id'] for r in rows],
                'category': [r['category'] for r in rows], 'input_ids': [r['input_ids'] for r in rows]}, out)
    print(f'wrote {out}', flush=True)


@torch.inference_mode()
def doc_stats(t, a, chunk=512):
    """Per document: (positions, sum KL, top-1 agreements, sum NLL teacher, sum NLL arm)."""
    wt, wa = t['lm_head'].to(DEVICE), a['lm_head'].to(DEVICE)
    out = []
    for d in range(len(t['ids'])):
        lo, hi = t['offsets'][d], t['offsets'][d + 1]
        nxt = torch.tensor(t['input_ids'][d][1:], device=DEVICE)
        kl = agree = nt = na = 0.0
        for s in range(lo, hi - 1, chunk):
            e = min(s + chunk, hi - 1)
            lt = torch.log_softmax((t['hidden'][s:e].to(DEVICE) @ wt.T).float(), -1)
            la = torch.log_softmax((a['hidden'][s:e].to(DEVICE) @ wa.T).float(), -1)
            kl += float((lt.exp() * (lt - la)).sum())
            agree += float((lt.argmax(-1) == la.argmax(-1)).sum())
            y = nxt[s - lo:e - lo]
            nt -= float(lt.gather(1, y[:, None]).sum())
            na -= float(la.gather(1, y[:, None]).sum())
        out.append((hi - lo - 1, kl, agree, nt, na))
    return out


def ci(per_doc, f, n=2000, seed=0):
    """Point estimate and 95% bootstrap interval of f(list of doc rows), docs resampled."""
    rnd = random.Random(seed)
    point = f(per_doc)
    boot = sorted(f([per_doc[rnd.randrange(len(per_doc))] for _ in per_doc]) for _ in range(n))
    return point, boot[int(0.025 * n)], boot[int(0.975 * n)]


def summary(rows):
    pos = sum(r[0] for r in rows)
    return {'kl': sum(r[1] for r in rows) / pos, 'top1': sum(r[2] for r in rows) / pos,
            'nll_rel': sum(r[4] for r in rows) / sum(r[3] for r in rows) - 1}


def compare(out_dir, teacher, *arms):
    t = torch.load(teacher)
    cats = sorted(set(t['category']))
    result, stats = {}, {}
    for path in arms:
        a = torch.load(path)
        assert a['ids'] == t['ids'], path
        stats[path] = doc_stats(t, a)
        name = os.path.basename(path)[:-3]
        res = {'sources': a['sources'], 'replaced': a['replaced']}
        for c in ['all'] + cats:
            docs = [r for r, k in zip(stats[path], t['category']) if c == 'all' or k == c]
            res[c] = {m: ci(docs, lambda rs, m=m: summary(rs)[m]) for m in ('kl', 'top1', 'nll_rel')}
        result[name] = res
        s = res['all']
        print(f"{name:28s} KL {s['kl'][0]:.4f} [{s['kl'][1]:.4f}, {s['kl'][2]:.4f}]  "
              f"top-1 {100 * s['top1'][0]:.2f}%  NLL {100 * s['nll_rel'][0]:+.2f}%", flush=True)
        print('    ' + '  '.join(f"{c} {res[c]['kl'][0]:.4f}" for c in cats), flush=True)
    base = arms[0]
    for path in arms[1:]:
        pairs = list(zip(stats[base], stats[path]))
        d = ci(pairs, lambda ps: summary([q for _, q in ps])['kl'] - summary([p for p, _ in ps])['kl'])
        wins = sum(1 for p, q in pairs if q[1] / q[0] < p[1] / p[0])
        name = os.path.basename(path)[:-3]
        result[name]['paired_vs_' + os.path.basename(base)[:-3]] = {'kl_delta': d, 'docs_lower': wins, 'docs': len(pairs)}
        print(f'{name} - {os.path.basename(base)[:-3]}: KL {d[0]:+.4f} [{d[1]:+.4f}, {d[2]:+.4f}], '
              f'lower on {wins}/{len(pairs)} docs', flush=True)
    json.dump(result, open(os.path.join(out_dir, 'kl-compare.json'), 'w'), indent=1)


if __name__ == '__main__':
    cmd, args = sys.argv[1], sys.argv[2:]
    {'states': states, 'compare': compare}[cmd](*args)
