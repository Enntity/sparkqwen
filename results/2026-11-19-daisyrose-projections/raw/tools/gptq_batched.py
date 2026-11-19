# SPDX-License-Identifier: AGPL-3.0-only
"""GPTQ for NVFP4 over many expert matrices at once.

The recipe is SparkDrama's (sparkdrama/docs/QUANT_SPEC.md v1.1 section 2):
damping 0.01 * mean(diag H), columns in descending diag(H) order, static
per-16 E4M3 scales chosen by MSE search before the sweep, block 128. The scale
search, the per-tensor scale and the E2M1 rounding are sparkdrama's functions,
unchanged; only the column sweep is batched over experts, because a Python
loop of 4,096 columns per matrix is too slow for 36,288 matrices.
tests/test_gptq_batched.py pins the result to sparkdrama's gptq_quantize.

Tensors that share an input (an expert's gate_proj and up_proj) share a
Hessian and go through one sweep stacked along rows; each keeps its own
per-tensor scale, as in the ModelOpt layout.
"""
import torch

from sparkdrama.quant.fp4 import GROUP, e2m1_pack, e2m1_round
from sparkdrama.quant.scale import mse_group_scale, per_tensor_scale, quantize_rtn

BLOCK = 128
DAMP = 0.01
MIN_TOKENS_GPTQ = 256


SPEC_RANGE = (0.80, 1.00)      # QUANT_SPEC v1.1's scale grid, as multiples of amax_g / 6
WIDE_RANGE = (0.80, 1.75)      # also scales that put a group's largest value below level 6


def _static_scales(w: torch.Tensor, scale_range=SPEC_RANGE) -> tuple[torch.Tensor, torch.Tensor]:
    """[N, K] -> (E4M3-valued group scales [N, K/16], per-tensor scale)."""
    n, k = w.shape
    s2 = per_tensor_scale(w).to(w.device)
    return mse_group_scale(w.reshape(n, k // GROUP, GROUP), s2, scale_range), s2


def _factor(h: torch.Tensor) -> torch.Tensor:
    """Damped, permuted H [E, K, K] -> upper Cholesky factor U of H^-1 (H^-1 = U^T U).

    With both index orders reversed, H's lower factor becomes an upper R with
    H = R R^T, so H^-1 = (R^-1)^T (R^-1) and U = R^-1: one factorization and one
    triangular inverse, instead of an inverse and a second factorization. U is
    unique, so this is the same matrix."""
    r = torch.linalg.cholesky(h.flip(-2, -1)).flip(-2, -1)
    eye = torch.eye(h.shape[-1], dtype=h.dtype, device=h.device).expand_as(h)
    return torch.linalg.solve_triangular(r, eye, upper=True)


@torch.no_grad()
def gptq_batched(
    ws: list[torch.Tensor],
    hessian: torch.Tensor,
    factor_dtype: torch.dtype = torch.float64,
    damp: float = DAMP,
    scale_range: tuple[float, float] = SPEC_RANGE,
) -> list[dict[str, torch.Tensor]]:
    """Quantize tensors that share an input.

    ws: tensors [E, N_i, K] (float), same E and K. hessian: [E, K, K].
    Returns one dict per tensor: `weight` uint8 [E, N_i, K/2], `weight_scale`
    uint8 E4M3 [E, N_i, K/16], `weight_scale_2` float32 [E], and `dequant`
    float32 [E, N_i, K], the value the stored bytes decode to.
    """
    e, _, k = ws[0].shape
    rows = [w.shape[1] for w in ws]
    w = torch.cat([x.float() for x in ws], dim=1)
    n = w.shape[1]
    h = hessian.to(factor_dtype).clone()

    diag = h.diagonal(dim1=-2, dim2=-1)
    dead = diag <= 0
    diag[dead] = 1.0
    w.masked_fill_(dead[:, None, :], 0.0)

    perm = torch.argsort(diag, dim=-1, descending=True)
    h = h.gather(1, perm[:, :, None].expand(e, k, k)).gather(2, perm[:, None, :].expand(e, k, k))
    h.diagonal(dim1=-2, dim2=-1).add_((damp * h.diagonal(dim1=-2, dim2=-1).mean(-1))[:, None])
    u = _factor(h).float()
    del h

    # Static scales on the stored column order, fixed before the sweep.
    scales = torch.empty(e, n, k // GROUP, device=w.device)
    s2 = torch.empty(e, len(ws), device=w.device)
    s2_row = torch.empty(e, n, 1, device=w.device)
    r0 = 0
    for ti, nr in enumerate(rows):
        for ei in range(e):
            sc, t2 = _static_scales(w[ei, r0:r0 + nr], scale_range)
            scales[ei, r0:r0 + nr] = sc
            s2[ei, ti] = t2
            s2_row[ei, r0:r0 + nr] = t2
        r0 += nr

    group_of = (perm // GROUP)[:, None, :].expand(e, n, k)
    sp = scales.gather(2, group_of)                       # scale of each permuted column
    wp = w.gather(2, perm[:, None, :].expand(e, n, k))
    q = torch.empty_like(wp)
    for bs in range(0, k, BLOCK):
        be = min(bs + BLOCK, k)
        wb = wp[:, :, bs:be].clone()
        err_b = torch.zeros_like(wb)
        for j in range(be - bs):
            c = bs + j
            sj = sp[:, :, c:c + 1]
            wj = wb[:, :, j:j + 1]
            qj = e2m1_round(wj / (sj * s2_row))
            q[:, :, c:c + 1] = qj
            err = (wj - qj * sj * s2_row) / u[:, c, c][:, None, None]
            wb[:, :, j + 1:] -= err * u[:, c, c + 1:be][:, None, :]
            err_b[:, :, j:j + 1] = err
        if be < k:
            wp[:, :, be:] -= torch.bmm(err_b, u[:, bs:be, be:])
    del wp, sp, u

    inv = torch.empty_like(perm)
    inv.scatter_(1, perm, torch.arange(k, device=perm.device).expand(e, k))
    q = q.gather(2, inv[:, None, :].expand(e, n, k))

    out = []
    r0 = 0
    for ti, nr in enumerate(rows):
        qt, st = q[:, r0:r0 + nr], scales[:, r0:r0 + nr]
        packed = torch.stack([e2m1_pack(qt[ei]) for ei in range(e)])
        deq = qt * st.repeat_interleave(GROUP, dim=2) * s2[:, ti][:, None, None]
        out.append({
            "weight": packed,
            "weight_scale": st.to(torch.float8_e4m3fn).view(torch.uint8),
            "weight_scale_2": s2[:, ti].clone(),
            "dequant": deq,
        })
        r0 += nr
    return out


@torch.no_grad()
def rtn_batched(ws: list[torch.Tensor], scale_range: tuple[float, float] = SPEC_RANGE) -> list[dict[str, torch.Tensor]]:
    """Round-to-nearest with the same scale search (the under-256-token path)."""
    from sparkdrama.quant.scale import dequant_ref

    out = []
    for w in ws:
        per = [quantize_rtn(w[ei].float(), scale_range) for ei in range(w.shape[0])]
        out.append({
            "weight": torch.stack([p["weight"] for p in per]),
            "weight_scale": torch.stack([p["weight_scale"] for p in per]),
            "weight_scale_2": torch.cat([p["weight_scale_2"].to(w.device) for p in per]),
            "dequant": torch.stack([dequant_ref(p) for p in per]),
        })
    return out
