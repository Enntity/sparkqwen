# SPDX-License-Identifier: AGPL-3.0-only
"""Sequential GPTQ for NVFP4: Hessian per module from its calibration inputs,
damping 0.01*mean(diag H), act_order, GPTQ block 128, static groups of 16 whose
FP8 scale is chosen per group by MSE search before the column updates.
Experts with <256 calibration tokens fall back to RTN (quantize_rtn)."""
import torch

from sparkdrama.quant.fp4 import GROUP, e2m1_round
from sparkdrama.quant.scale import mse_group_scale, per_tensor_scale, quantize_rtn

MIN_TOKENS_GPTQ = 256
BLOCK = 128


def hessian_add(H: torch.Tensor, x: torch.Tensor) -> torch.Tensor:
    x2 = x.reshape(-1, x.shape[-1]).double()
    H.addmm_(x2.T, x2)
    return H


def gptq_quantize(w: torch.Tensor, H: torch.Tensor) -> dict[str, torch.Tensor]:
    """GPTQ on a [N, K] weight given Hessian H [K, K].

    act_order: columns quantized in descending diag(H) order; groups of 16
    static scales fixed before the sweep; per-128 column Cholesky updates.
    """
    w = w.float()
    n, k = w.shape
    dead = H.diagonal() <= 0
    H = H.clone()
    H[dead, dead] = 1.0
    w[:, dead] = 0.0

    perm = torch.argsort(H.diagonal(), descending=True)
    w_perm = w[:, perm]
    H_perm = H[perm][:, perm]

    damp = 0.01 * H_perm.diagonal().mean()
    H_perm.diagonal().add_(damp)
    # GPTQ update matrix: upper-triangular Cholesky factor of H^-1, so that
    # entries [j, j:] define the error propagation to future columns.
    Hinv = torch.cholesky_inverse(torch.linalg.cholesky(H_perm))
    Hinv = torch.linalg.cholesky(Hinv, upper=True)

    W = w_perm.clone()
    Q = torch.zeros_like(W)

    # static per-16-group scales on the ORIGINAL column order (the storage
    # layout), fixed before the sweep; permuted column c uses group
    # perm[c] // GROUP.
    s2 = per_tensor_scale(w)
    wg = w.reshape(n, k // GROUP, GROUP)
    scales = mse_group_scale(wg, s2)  # [n, k/16], original order

    for bs in range(0, k, BLOCK):
        be = min(bs + BLOCK, k)
        Wb = W[:, bs:be].clone()
        Qb = torch.zeros_like(Wb)
        Err = torch.zeros_like(Wb)
        for j in range(be - bs):
            g = int(perm[bs + j].item()) // GROUP
            sj = scales[:, g]
            wj = Wb[:, j]
            q = e2m1_round(wj / (sj * s2))
            Qb[:, j] = q
            d = Hinv[bs + j, bs + j]
            err = (wj - q * sj * s2) / d
            Wb[:, j + 1:] -= err.unsqueeze(1) * Hinv[bs + j, bs + j + 1 : be].unsqueeze(0)
            Err[:, j] = err
        Q[:, bs:be] = Qb
        # propagate accumulated block error to columns after this block
        if be < k:
            W[:, be:] -= Err @ Hinv[bs:be, be:]

    # map back to original column order
    inv_perm = torch.empty_like(perm)
    inv_perm[perm] = torch.arange(k, device=perm.device)
    Q_orig = Q[:, inv_perm]

    from sparkdrama.quant.fp4 import e2m1_pack
    packed = e2m1_pack(Q_orig)
    return {
        "weight": packed,
        "weight_scale": scales.to(torch.float8_e4m3fn).view(torch.uint8),
        "weight_scale_2": s2.reshape(1),
    }


def quantize_with_hessian(
    w: torch.Tensor, H: torch.Tensor | None
) -> dict[str, torch.Tensor]:
    """GPTQ if enough calibration tokens, else RTN (spec §3)."""
    if H is None or H.diagonal().min() <= 0:
        return quantize_rtn(w)
    return gptq_quantize(w, H)
