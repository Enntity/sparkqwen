<!-- SPDX-License-Identifier: AGPL-3.0-only -->
# SparkQwen cards

`banner.png` is the README hero (2172 × 724). `social-preview.png` is the
matching social card (1733 × 907); `social-preview.jpg` is its same-dimension
JPEG export, below 1 MB.

The cards show the two models SparkQwen serves and how to pick one:
Qwen3.8-27B on one DGX Spark (`./start.sh --model 27b`; NVFP4, DFlash2 with
exact verify, 262,144-token requests; a candidate that is not yet qualified) and
Qwen3.8-Flash-Next on two DGX Sparks at TP=2 (`./start.sh --model flash-next`,
the default; FP4-Local, native MTP, up to 262,144-token requests by profile).

They were composed on 2026-11-10 by [`make_cards.py`](make_cards.py) from the
0.4.0 cards (this directory at commit `a0d38a3`), which the built-in image
generation tool had produced from [these prompts](PROMPTS.md). The script
keeps the purple arcade frame, starfield, logo, title lettering, wireframe
tunnel and URL as they were, paints out the version, subtitle, metric columns
and supporting lines, and sets the new text in Press Start 2P (SIL Open Font
License 1.1; the font is not shipped here):

```sh
python3 docs/assets/make_cards.py OLD_CARDS_DIR PressStart2P-Regular.ttf docs/assets
```

Both cards were visually checked. The cards carry no version number.

The only figures on them are historical **0.3.1** Flash-Next measurements,
labelled as such: code **106.4 tok/s** and cold 16K prefill **4,142 tok/s**
(RigMark 1.1.0, low effort). They use the first passing complete run of two
scheduled runs; both runs and all repetitions are in the
[qualification report](../../results/2026-10-24-common-engine/RESULT.md).
The 27B lane shows no figure: it has no qualification run yet.

"Exact verify" is on the 27B lane only and means what the main README says
there: text byte-identical to serial decode. The guard line describes the
default-on pattern filter, not protection from all exfiltration. See
[coverage and limits](../TOOL-GUARD.md).

Committing these files does not itself update GitHub's saved social preview.
