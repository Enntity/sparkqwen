# SPDX-License-Identifier: AGPL-3.0-only
import os
import sys

import torch

os.environ.setdefault('DEVICE', 'cpu')
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, '..', 'daisyrose-nvfp4-20261118', 'sparkdrama-b82c078', 'src'))

import kl_eval  # noqa: E402
from sparkdrama.quant import fp4  # noqa: E402
from sparkdrama.quant.scale import quantize_rtn  # noqa: E402


def test_nvfp4_dequant_matches_sparkdrama():
    torch.manual_seed(0)
    w = torch.randn(32, 64)
    q = quantize_rtn(w)
    ref = fp4.dequantize(q['weight'], q['weight_scale'], q['weight_scale_2'])
    got = kl_eval.nvfp4_dequant(q['weight'], q['weight_scale'].view(torch.float8_e4m3fn), q['weight_scale_2'])
    assert torch.equal(got, ref)


def test_rtn_is_on_the_nvfp4_grid_and_idempotent():
    torch.manual_seed(1)
    w = torch.randn(16, 128) * 0.02
    d = kl_eval.nvfp4_rtn(w)
    assert torch.equal(kl_eval.nvfp4_rtn(d), d)
    assert ((d - w).norm() / w.norm()) < 0.15
    # a block's largest value lands exactly on +-6 * its scale
    s2 = w.abs().max() / (6 * 448)
    g = d.reshape(16, 8, 16)
    s = (w.reshape(16, 8, 16).abs().amax(-1) / 6 / s2).to(torch.float8_e4m3fn).float()
    assert torch.allclose(g.abs().amax(-1), 6 * s * s2, rtol=1e-6)


def test_rtn_shared_amax_sets_scale_2():
    torch.manual_seed(2)
    w = torch.randn(4, 32)
    big = float(w.abs().max()) * 3
    d = kl_eval.nvfp4_rtn(w, big)
    s2 = big / (6 * 448)
    s = (w.reshape(4, 2, 16).abs().amax(-1) / 6 / s2).to(torch.float8_e4m3fn).float()
    assert torch.allclose(d.reshape(4, 2, 16).abs().amax(-1), 6 * s * s2, rtol=1e-6)
    assert not torch.equal(d, kl_eval.nvfp4_rtn(w))


def test_fp8_dequant_scalar_and_rows():
    w = torch.tensor([[1.0, -2.0], [0.5, 4.0]]).to(torch.float8_e4m3fn)
    assert torch.equal(kl_eval.fp8_dequant(w, torch.tensor(0.5)), torch.tensor([[0.5, -1.0], [0.25, 2.0]]))
    assert torch.equal(kl_eval.fp8_dequant(w, torch.tensor([2.0, 1.0])), torch.tensor([[2.0, -4.0], [0.5, 4.0]]))


def test_tie_scale_matches_the_overlay_tool():
    sys.path.insert(0, os.path.join(HERE, '..', '..', 'sparkqwen', 'install'))
    import tandem_overlay
    codes = torch.arange(0, 0x7F, dtype=torch.uint8)
    s2z, s2q = torch.tensor(3e-4), torch.tensor(5e-4)
    got = kl_eval.tie_scale(codes.view(torch.float8_e4m3fn), s2z, s2q).view(torch.uint8)
    want = torch.tensor(list(bytes(codes.tolist()).translate(tandem_overlay.rescale_table(float(s2z / s2q)))),
                        dtype=torch.uint8)
    assert torch.equal(got, want)


def test_summary_and_ci():
    rows = [(10, 1.0, 9, 20.0, 22.0), (10, 3.0, 7, 20.0, 18.0)]
    s = kl_eval.summary(rows)
    assert abs(s['kl'] - 0.2) < 1e-12 and abs(s['top1'] - 0.8) < 1e-12 and abs(s['nll_rel']) < 1e-12
    p, lo, hi = kl_eval.ci(rows, lambda r: kl_eval.summary(r)['kl'], n=200)
    assert lo <= p <= hi and 0.1 <= lo and hi <= 0.3
