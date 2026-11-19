# SPDX-License-Identifier: AGPL-3.0-only
"""NVFP4 primitive: E2M1 values + FP8 E4M3 per-16 scales + F32 per-tensor scale.

Layout matches Atlas's ModelOpt loader (nvfp4_detect.rs /
dequant_nvfp4_bf16.cu): `.weight` = packed uint8 [N, K/2], even column in the
low nibble, odd in the high; `.weight_scale` = FP8 E4M3 [N, K/16];
`.weight_scale_2` = F32 scalar; `.input_scale` = F32 scalar.
"""
import torch

E2M1_LUT = torch.tensor(  # full nibble table: index = nibble value
    [0.0, 0.5, 1.0, 1.5, 2.0, 3.0, 4.0, 6.0,
     -0.0, -0.5, -1.0, -1.5, -2.0, -3.0, -4.0, -6.0],
    dtype=torch.float32,
)
E2M1_ABS = E2M1_LUT[:8]
E4M3_MAX = 448.0
GROUP = 16


# Midpoints between neighbouring E2M1 magnitudes; a value on a midpoint takes
# the smaller magnitude (bucketize's default side).
E2M1_MID = torch.tensor([0.25, 0.75, 1.25, 1.75, 2.5, 3.5, 5.0], dtype=torch.float32)


def e2m1_codes(q: torch.Tensor) -> torch.Tensor:
    """Nearest E2M1 nibble index (0-15, sign in bit 3) per element."""
    idx = torch.bucketize(q.abs(), E2M1_MID.to(q.device, q.dtype)).to(torch.uint8)
    neg = (q < 0) | ((q == 0) & torch.signbit(q))
    return idx | (neg.to(torch.uint8) << 3)


def e2m1_round(x: torch.Tensor) -> torch.Tensor:
    """Round float tensor to the nearest E2M1 value (ties to smaller abs)."""
    return E2M1_LUT.to(x.device)[e2m1_codes(x).long()]


def e2m1_pack(q: torch.Tensor) -> torch.Tensor:
    """Pack E2M1-rounded values [N, K] into uint8 nibbles [N, K/2].

    Even column -> low nibble, odd column -> high nibble (Atlas CPU packing).
    """
    codes = e2m1_codes(q)
    even, odd = codes[:, 0::2], codes[:, 1::2]
    return (odd << 4) | even


def e2m1_unpack(packed: torch.Tensor) -> torch.Tensor:
    """Unpack uint8 [N, K/2] back to float [N, K] via the LUT."""
    lut = E2M1_LUT.to(packed.device)
    even = lut[(packed & 0xF).long()]
    odd = lut[((packed >> 4) & 0xF).long()]
    return torch.stack([even, odd], dim=-1).flatten(1)


def e4m3_round(x: torch.Tensor) -> torch.Tensor:
    """Round to FP8 E4M3 (4 exp, 3 mantissa, bias 7, no inf, NaN->0)."""
    xf = x.to(torch.float32)
    if not hasattr(torch, "float8_e4m3fn"):
        raise RuntimeError("torch lacks float8_e4m3fn")
    return xf.to(torch.float8_e4m3fn)


def e4m3_encode(x: torch.Tensor) -> torch.Tensor:
    """Encode float tensor to E4M3 byte representation (uint8 view)."""
    return e4m3_round(x).view(torch.uint8)


def e4m3_decode(b: torch.Tensor) -> torch.Tensor:
    return b.to(torch.uint8).view(torch.float8_e4m3fn).to(torch.float32)


def dequantize(packed: torch.Tensor, scale: torch.Tensor,
               scale2: torch.Tensor) -> torch.Tensor:
    """NVFP4 dequant: values = E2M1 * e4m3_scale * scale2, groups of 16."""
    values = e2m1_unpack(packed).float()
    s = e4m3_decode(scale).float()
    n, k = values.shape
    values = values * s.repeat_interleave(16, dim=1)[:, :k] * float(scale2)
    return values
