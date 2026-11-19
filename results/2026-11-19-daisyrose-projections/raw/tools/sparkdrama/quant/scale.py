# SPDX-License-Identifier: AGPL-3.0-only
"""NVFP4 scale search: per-16 FP8 E4M3 scale by MSE over
amax_g/6 * {1.00, 0.99, ..., 0.80} (candidates rounded to E4M3), plus the
per-tensor F32 scale amax/(6*448) from QUANT_SPEC.md."""
import torch

from sparkdrama.quant.fp4 import E4M3_MAX, E2M1_ABS, e2m1_round, e4m3_decode, e4m3_round

GROUP = 16
SCALE_FACTORS = [1.00 - 0.01 * i for i in range(21)]  # 1.00 .. 0.80


def mse_group_scale(w_group: torch.Tensor, s2: torch.Tensor,
                    factors: tuple[float, float] = (SCALE_FACTORS[-1], SCALE_FACTORS[0])) -> torch.Tensor:
    """Per-group E4M3 scale minimizing MSE over the candidate grid.

    w_group: [.., 16] float weights. s2: per-tensor F32 scale (amax/(6*448)).
    factors: (lowest, highest) multiple of amax_g/6 to try; the spec's grid is
    (0.80, 1.00). A highest above 1 also tries scales that put the group's
    largest value below E2M1's top level 6 (at 1.5 it lands on 4), which
    spends the levels more evenly and is often the better choice.
    Returns e4m3 float scale values (not bytes).
    """
    amax = w_group.abs().max(-1).values.clamp(min=1e-8)
    base = amax / 6.0 / s2  # candidate scale before the grid
    # A 1% grid is finer than E4M3's spacing, so its candidates are exactly
    # the E4M3 codes from round(highest * base) down to round(lowest * base).
    # Try each code once, largest first; a later one wins only if strictly
    # better, as the grid's order had it.
    hi = e4m3_round((base * factors[1]).clamp(max=E4M3_MAX)).view(torch.uint8).to(torch.int16)
    lo = e4m3_round((base * factors[0]).clamp(max=E4M3_MAX)).view(torch.uint8).to(torch.int16)
    best_s = None
    best_err = None
    for k in range(int((hi - lo).max()) + 1):
        code = (hi - k).clamp(min=0)
        cand = e4m3_decode(code.to(torch.uint8)).clamp(min=1e-12)
        q = e2m1_round(w_group / (cand.unsqueeze(-1) * s2))
        err = ((w_group - q * cand.unsqueeze(-1) * s2) ** 2).mean(-1)
        if best_err is None:
            best_err, best_s = err, cand
        else:
            take = (err < best_err) & (hi - k >= lo)
            best_err = torch.where(take, err, best_err)
            best_s = torch.where(take, cand, best_s)
    return best_s


def per_tensor_scale(w: torch.Tensor) -> torch.Tensor:
    """weight_scale_2 = amax / (6 * 448)."""
    return torch.tensor(
        float(w.abs().max()) / (6.0 * E4M3_MAX), dtype=torch.float32
    )


def quantize_rtn(w: torch.Tensor, factors: tuple[float, float] = (SCALE_FACTORS[-1], SCALE_FACTORS[0])
                 ) -> dict[str, torch.Tensor]:
    """Round-to-nearest NVFP4 quantization of a [N, K] weight.

    Returns ModelOpt fields: weight (uint8 [N,K/2]), weight_scale (uint8 E4M3
    [N,K/16]), weight_scale_2 (F32 scalar).
    """
    w = w.float()
    n, k = w.shape
    assert k % GROUP == 0
    s2 = per_tensor_scale(w)
    wg = w.reshape(n, k // GROUP, GROUP)
    s = mse_group_scale(wg, s2, factors)  # [n, k/16] float
    q = e2m1_round(wg / (s.unsqueeze(-1) * s2))
    packed = _pack_rows(q.reshape(n, k))
    return {
        "weight": packed,
        "weight_scale": s.to(torch.float8_e4m3fn).view(torch.uint8),
        "weight_scale_2": s2.reshape(1),
    }


def _pack_rows(q: torch.Tensor) -> torch.Tensor:
    from sparkdrama.quant.fp4 import e2m1_pack
    return e2m1_pack(q)


def dequant_ref(t: dict[str, torch.Tensor]) -> torch.Tensor:
    from sparkdrama.quant.fp4 import dequantize
    return dequantize(t["weight"], t["weight_scale"], t["weight_scale_2"])
