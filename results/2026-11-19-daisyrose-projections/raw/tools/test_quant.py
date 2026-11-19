# SPDX-License-Identifier: AGPL-3.0-only
"""CPU checks for quant_daisyrose.py on a tiny random qwen3_5 text model."""
import os
os.environ['DEVICE'] = 'cpu'
import torch
import quant_daisyrose as q
from sparkdrama.quant.fp4 import dequantize
from sparkdrama.quant.scale import quantize_rtn


def tiny():
    from transformers import Qwen3_5TextConfig, Qwen3_5TextModel
    cfg = Qwen3_5TextConfig(vocab_size=128, hidden_size=64, intermediate_size=128, num_hidden_layers=4,
                            num_attention_heads=4, num_key_value_heads=2, head_dim=16, full_attention_interval=4,
                            linear_num_key_heads=2, linear_num_value_heads=4, linear_key_head_dim=16,
                            linear_value_head_dim=16, linear_conv_kernel_dim=4)
    torch.manual_seed(0)
    return Qwen3_5TextModel(cfg).eval()


def test_targets_follow_the_layer_types():
    t = q.targets(tiny())
    assert [(i, m) for i, m, _, _ in t] == [(0, 'linear_attn'), (1, 'linear_attn'), (2, 'linear_attn'), (3, 'self_attn')]
    for _, m, groups, mod in t:
        for projs in groups.values():
            for p in projs:
                assert isinstance(getattr(mod, p), torch.nn.Linear), (m, p)


def test_hessian_is_the_inputs_second_moment():
    model = tiny()
    seen_x = []
    h = model.layers[3].self_attn.k_proj.register_forward_pre_hook(lambda _m, a: seen_x.append(a[0].reshape(-1, 64).float()))
    rows = [{'input_ids': [1, 5, 9, 3, 7, 2]}, {'input_ids': [4, 4, 8]}]
    H, seen = q.hessians(model, rows)
    h.remove()
    assert seen == 9
    x = torch.cat(seen_x)
    torch.testing.assert_close(H[(3, 'q_proj')], x.T @ x, rtol=1e-5, atol=1e-5)  # q, k, v share it
    _, capped = q.hessians(model, rows, max_tokens=7)
    assert capped == 7


def test_tandem_layout_and_gptq_beats_rtn_on_its_inputs():
    torch.manual_seed(1)
    w = torch.randn(32, 64)
    x = torch.randn(512, 64) @ torch.randn(64, 64)  # correlated inputs, where GPTQ helps
    H = x.T @ x
    out = q.as_tandem(7, 'linear_attn', 'out_proj', q.gptq_quantize(w, H))
    wn, sn, s2n = q.tensor_names(7, 'linear_attn', 'out_proj')
    assert set(out) == {wn, sn, s2n} and wn == 'layers.7.linear_attn.out_proj.weight'
    assert out[wn].dtype == torch.uint8 and tuple(out[wn].shape) == (32, 32)
    assert out[sn].dtype == torch.float8_e4m3fn and tuple(out[sn].shape) == (32, 4)
    assert out[s2n].dtype == torch.float32 and out[s2n].shape == ()
    gptq = dequantize(out[wn], out[sn].view(torch.uint8), out[s2n])
    r = quantize_rtn(w)
    rtn = dequantize(r['weight'], r['weight_scale'], r['weight_scale_2'])
    assert q.rel_error(w, w, H) == 0
    assert q.rel_error(w, gptq, H) < q.rel_error(w, rtn, H)


def test_streamed_load_matches_the_model(tmp_path):
    import json
    from safetensors.torch import save_file
    model = tiny().to(torch.bfloat16)
    sd = {q.PREFIX + k: v.contiguous() for k, v in model.state_dict().items()}
    names = sorted(sd)
    save_file({k: sd[k] for k in names[::2]}, str(tmp_path / 'a.safetensors'))
    save_file({k: sd[k] for k in names[1::2]}, str(tmp_path / 'b.safetensors'))
    index = {k: 'a.safetensors' for k in names[::2]} | {k: 'b.safetensors' for k in names[1::2]}
    index['model.visual.x.weight'] = 'a.safetensors'  # other towers are skipped
    (tmp_path / 'model.safetensors.index.json').write_text(json.dumps({'weight_map': index}))
    (tmp_path / 'config.json').write_text(json.dumps({'text_config': model.config.to_dict()}))
    _, loaded = q.load(str(tmp_path))
    ids = torch.tensor([[3, 1, 4, 1, 5, 9, 2, 6]])
    with torch.inference_mode():
        torch.testing.assert_close(loaded(input_ids=ids).last_hidden_state, model(input_ids=ids).last_hidden_state,
                                   rtol=0, atol=0)


def test_batched_group_matches_sparkdramas_gptq_at_the_spec_settings():
    torch.manual_seed(2)
    x = torch.randn(512, 64) @ torch.randn(64, 64)
    H = x.T @ x
    ws = [torch.randn(32, 64), torch.randn(16, 64)]
    got = q.quantize_group(ws, H, 0.01, (0.80, 1.00))
    for w, (qq, deq) in zip(ws, got):
        ref = q.gptq_quantize(w, H)
        torch.testing.assert_close(dequantize(qq['weight'], qq['weight_scale'], qq['weight_scale_2']),
                                   dequantize(ref['weight'], ref['weight_scale'], ref['weight_scale_2']), rtol=0, atol=1e-6)
        torch.testing.assert_close(deq, dequantize(qq['weight'], qq['weight_scale'], qq['weight_scale_2']), rtol=0, atol=1e-6)


def test_wide_scales_cut_the_error_on_heavy_tailed_weights():
    torch.manual_seed(3)
    x = torch.randn(512, 64) @ torch.randn(64, 64)
    H = x.T @ x
    w = torch.distributions.StudentT(3.0).sample((64, 64))
    spec = q.quantize_group([w], H, 0.1, (0.80, 1.00))[0][1]
    wide = q.quantize_group([w], H, 0.1, (0.80, 1.75))[0][1]
    assert q.rel_error(w, wide, H) < q.rel_error(w, spec, H)
