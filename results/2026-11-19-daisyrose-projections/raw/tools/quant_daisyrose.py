# SPDX-License-Identifier: AGPL-3.0-only
"""NVFP4 Gated DeltaNet and attention projections for RadixArk/DaisyRose-27B.

  quant_daisyrose.py calib BF16_DIR CALIB_JSONL OUT_DIR [DAMP=0.01] [SCALE_RANGE=0.80,1.00] [HESSIANS]
  quant_daisyrose.py report BF16_DIR EVAL_JSONL OUT_DIR FP8_DIR [EVAL_TOKENS]

calib: runs the BF16 model (transformers' qwen3_5) over the calibration rows,
records H = X^T X (float32) of every target projection's input (or reads them
from HESSIANS, a torch file written by an earlier run with that path), quantizes
the projections that share an input in one GPTQ sweep (gptq_batched.py, pinned
to SparkDrama's gptq_quantize: damping DAMP * mean diag H, act_order, block
128, a per-16 E4M3 scale chosen by MSE over amax_g/6 * SCALE_RANGE in E4M3
steps, weight_scale_2 = amax / (6 * 448) per tensor) and writes
OUT_DIR/gdn.safetensors and OUT_DIR/attn.safetensors in TandemLLM's layout
(`layers.N.<linear_attn|self_attn>.<proj>.{weight,weight_scale,weight_scale_2}`),
so SparkQwen's install/tandem_overlay.py can lay them over the NVFP4 checkpoint.
Hessians come from the unquantized model (one pass), as TandemLLM's did.

report: the same pass over held-out rows, then each projection's relative output
error tr(dW H dW^T) / tr(W H W^T) for our GPTQ weights, RTN with the same scale
search, and the checkpoint's own FP8 weights (FP8_DIR, the published NVFP4
checkpoint): OUT_DIR/report.json.
"""
import json
import os
import sys
import time

import torch
from safetensors import safe_open
from safetensors.torch import save_file

from sparkdrama.quant.fp4 import dequantize
from sparkdrama.quant.gptq import gptq_quantize
from sparkdrama.quant.scale import quantize_rtn

from gptq_batched import gptq_batched

DEVICE = os.environ.get('DEVICE', 'cuda')

# Projections sharing an input share one Hessian (keyed by the first).
GDN = {'in_proj_qkv': ['in_proj_qkv', 'in_proj_z'], 'out_proj': ['out_proj']}
ATTN = {'q_proj': ['q_proj', 'k_proj', 'v_proj'], 'o_proj': ['o_proj']}


def targets(text_model):
    """[(layer, module_name, {hessian_key: [proj, ...]}, module)] for every layer."""
    out = []
    for i, layer in enumerate(text_model.layers):
        if hasattr(layer, 'linear_attn'):
            out.append((i, 'linear_attn', GDN, layer.linear_attn))
        else:
            out.append((i, 'self_attn', ATTN, layer.self_attn))
    return out


def tensor_names(i, module, proj):
    base = f'layers.{i}.{module}.{proj}'
    return base + '.weight', base + '.weight_scale', base + '.weight_scale_2'


def as_tandem(i, module, proj, q):
    """SparkDrama's dict -> TandemLLM's dtypes: U8 codes, F8_E4M3 scales, F32 scalar."""
    w, s, s2 = tensor_names(i, module, proj)
    return {w: q['weight'].contiguous().cpu(),
            s: q['weight_scale'].view(torch.float8_e4m3fn).contiguous().cpu(),
            s2: q['weight_scale_2'].reshape(()).float().contiguous().cpu()}


def rel_error(w, wq, H):
    """Relative output error of wq against w for inputs whose second moment is H."""
    d = (wq - w).double()
    w = w.double()
    H = H.double()
    return float(torch.einsum('nk,kj,nj->', d, H, d) / torch.einsum('nk,kj,nj->', w, H, w))


PREFIX = 'model.language_model.'


def load(bf16_dir):
    """The text model only, each tensor read straight to DEVICE from its shard.

    from_pretrained allocated the whole model on the GPU and then staged the
    shards in host memory as well, which a GB10's shared memory cannot hold.
    """
    from transformers import Qwen3_5TextConfig, Qwen3_5TextModel
    cfg = Qwen3_5TextConfig(**json.load(open(os.path.join(bf16_dir, 'config.json')))['text_config'])
    with torch.device('meta'):
        text = Qwen3_5TextModel(cfg)
    index = json.load(open(os.path.join(bf16_dir, 'model.safetensors.index.json')))['weight_map']
    wanted = {n: p for n, p in text.named_parameters()} | {n: b for n, b in text.named_buffers()}
    by_shard = {}
    for name, shard in index.items():
        if name.startswith(PREFIX) and name[len(PREFIX):] in wanted:
            by_shard.setdefault(shard, []).append(name[len(PREFIX):])
    for shard, names in sorted(by_shard.items()):
        with safe_open(os.path.join(bf16_dir, shard), 'pt', device=DEVICE) as f:
            for name in names:
                owner, _, leaf = name.rpartition('.')
                mod = text.get_submodule(owner)
                t = f.get_tensor(PREFIX + name)
                if leaf in mod._parameters:
                    mod._parameters[leaf] = torch.nn.Parameter(t, requires_grad=False)
                else:
                    mod._buffers[leaf] = t
    # Non-persistent buffers (the rotary frequencies) are rebuilt, not read.
    with torch.device(DEVICE):
        text.rotary_emb = type(text.rotary_emb)(config=cfg)
    left = [n for n, t in list(text.named_parameters()) + list(text.named_buffers()) if t.is_meta]
    if left:
        raise SystemExit(f'not in the checkpoint: {left[:8]}')
    text.eval()
    return None, text


def hessians(text_model, rows, max_tokens=None):
    """Run rows through text_model; returns ({(layer, key): H}, tokens seen)."""
    H, hooks = {}, []
    for i, module, groups, mod in targets(text_model):
        for key in groups:
            lin = getattr(mod, key)
            H[(i, key)] = torch.zeros(lin.in_features, lin.in_features, dtype=torch.float32, device=DEVICE)

            def hook(_m, args, h=H[(i, key)]):
                x = args[0].reshape(-1, args[0].shape[-1]).float()
                h.addmm_(x.T, x)
            hooks.append(lin.register_forward_pre_hook(hook))
    seen, t0 = 0, time.time()
    try:
        with torch.inference_mode():
            for n, row in enumerate(rows):
                ids = row['input_ids']
                if max_tokens is not None:
                    ids = ids[:max(0, max_tokens - seen)]
                    if not ids:
                        break
                text_model(input_ids=torch.tensor([ids], device=DEVICE), use_cache=False)
                seen += len(ids)
                if n % 25 == 0:
                    print(f'  row {n}: {seen:,} tokens, {seen / (time.time() - t0):,.0f} tok/s', flush=True)
    finally:
        for h in hooks:
            h.remove()
    return H, seen


def read_rows(path):
    with open(path) as f:
        return [json.loads(line) for line in f]


def quantize_group(ws, h, damp, scale_range):
    """GPTQ of tensors [N_i, K] sharing Hessian h: SparkDrama-format dicts and their dequant."""
    out = gptq_batched([w[None] for w in ws], h[None], damp=damp, scale_range=scale_range)
    return [({'weight': o['weight'][0], 'weight_scale': o['weight_scale'][0],
              'weight_scale_2': o['weight_scale_2'][0]}, o['dequant'][0]) for o in out]


def calib(bf16_dir, calib_jsonl, out_dir, damp='0.01', scale_range='0.80,1.00', hessian_file=None):
    damp, scale_range = float(damp), tuple(float(x) for x in scale_range.split(','))
    os.makedirs(out_dir, exist_ok=True)
    model, text = load(bf16_dir)
    if hessian_file and os.path.exists(hessian_file):
        saved = torch.load(hessian_file, map_location=DEVICE)
        H, seen = saved['H'], saved['tokens']
    else:
        H, seen = hessians(text, read_rows(calib_jsonl))
        if hessian_file:
            torch.save({'H': H, 'tokens': seen}, hessian_file)
    print(f'calibration: {seen:,} tokens; damp {damp}, scale range {scale_range}', flush=True)
    files, errors = {'linear_attn': {}, 'self_attn': {}}, []
    for i, module, groups, mod in targets(text):
        for key, projs in groups.items():
            t = time.time()
            ws = [getattr(mod, proj).weight.detach().float() for proj in projs]
            for proj, w, (q, deq) in zip(projs, ws, quantize_group(ws, H[(i, key)], damp, scale_range)):
                files[module].update(as_tandem(i, module, proj, q))
                errors.append({'layer': i, 'proj': proj, 'calib_rel_error': rel_error(w, deq, H[(i, key)])})
            print(f'  layer {i} {"+".join(projs)} {time.time() - t:.1f}s '
                  + ' '.join(f'{e["calib_rel_error"]:.5f}' for e in errors[-len(projs):]), flush=True)
            del H[(i, key)]
    mean = sum(e['calib_rel_error'] for e in errors) / len(errors)
    print(f'mean calibration relative output error {mean:.5f}', flush=True)
    json.dump({'damp': damp, 'scale_range': scale_range, 'tokens': seen, 'mean': mean, 'rows': errors},
              open(os.path.join(out_dir, 'quant-report.json'), 'w'), indent=1)
    meta = {'source': 'RadixArk/DaisyRose-27B@293a7a2ab54aaea78098ee917c546390667521dc', 'source_kind': 'bf16',
            'calibration': os.path.basename(calib_jsonl), 'calibration_tokens': str(seen), 'format': 'nvfp4',
            'group': '16', 'mode': 'gptq', 'damp': str(damp), 'scale_range': '%g,%g x amax/6' % scale_range,
            'quantizer': 'gptq_batched.py on sparkdrama b82c078 + perf/fp4-fast-rounding',
            'made_by': 'experiments/daisyrose-nvfp4-20261118/quant_daisyrose.py'}
    save_file(files['linear_attn'], os.path.join(out_dir, 'gdn.safetensors'), {**meta, 'targets': 'gdn'})
    save_file(files['self_attn'], os.path.join(out_dir, 'attn.safetensors'), {**meta, 'targets': 'attn'})


def fp8_weight(fp8_dir, i, module, proj):
    index = json.load(open(os.path.join(fp8_dir, 'model.safetensors.index.json')))['weight_map']
    name = f'model.language_model.layers.{i}.{module}.{proj}'
    with safe_open(os.path.join(fp8_dir, index[name + '.weight']), 'pt', device=DEVICE) as f:
        w = f.get_tensor(name + '.weight').float()
    with safe_open(os.path.join(fp8_dir, index[name + '.weight_scale']), 'pt', device=DEVICE) as f:
        return w * f.get_tensor(name + '.weight_scale').float()


def report(bf16_dir, eval_jsonl, out_dir, fp8_dir, eval_tokens=120_000):
    model, text = load(bf16_dir)
    H, seen = hessians(text, read_rows(eval_jsonl), int(eval_tokens))
    ours = {}
    for name in ('gdn.safetensors', 'attn.safetensors'):
        with safe_open(os.path.join(out_dir, name), 'pt', device=DEVICE) as f:
            ours.update({k: f.get_tensor(k) for k in f.keys()})
    rows = []
    for i, module, groups, mod in targets(text):
        for key, projs in groups.items():
            for proj in projs:
                w = getattr(mod, proj).weight.detach().float()
                wn, sn, s2n = tensor_names(i, module, proj)
                gptq = dequantize(ours[wn], ours[sn].view(torch.uint8), ours[s2n])
                r = quantize_rtn(w)
                rtn = dequantize(r['weight'], r['weight_scale'], r['weight_scale_2'])
                h = H[(i, key)]
                rows.append({'layer': i, 'proj': proj, 'gptq': rel_error(w, gptq, h), 'rtn': rel_error(w, rtn, h),
                             'fp8': rel_error(w, fp8_weight(fp8_dir, i, module, proj), h)})
                print(json.dumps(rows[-1]), flush=True)
    mean = {k: sum(r[k] for r in rows) / len(rows) for k in ('gptq', 'rtn', 'fp8')}
    json.dump({'eval_tokens': seen, 'mean': mean, 'rows': rows}, open(os.path.join(out_dir, 'report.json'), 'w'), indent=1)
    print('mean relative output error', mean)


if __name__ == '__main__':
    cmd, args = sys.argv[1], sys.argv[2:]
    {'calib': calib, 'report': report}[cmd](*args)
