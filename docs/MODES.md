<!-- SPDX-License-Identifier: AGPL-3.0-only -->
# Strict and Spark

Set `MODE=strict` (the default) or `MODE=spark` in `.env`, or run
`./start.sh --mode spark`. Managed launchers pass `SPARKQWEN_MODE`; the per-node
entry point accepts `--mode strict|spark`. Use the same mode on both ranks. Custom profiles must select the Qwen kernel
target exactly once, retain TP2/EP2 and BF16 KV, and enable native speculation
with a positive draft count. Conflicting duplicate mode arguments are rejected.

Both modes use TP2/EP2, BF16 KV, the checkpoint's native target precision and
its native MTP head. HC and PLE norm weights remain F32; the target router and
LM head remain BF16; MXFP8 projections and the shared expert retain their
checkpoint representation. Native FP4 experts retain their checkpoint scales.
The loader rejects incompatible target formats instead of silently converting
them into an approximate execution path.

Strict uses BF16 attention and output projections in the MTP draft head.
Spark uses NVFP4 copies of those draft projections, with the corrected
round-to-nearest-even weight conversion. Target verification is present in both
modes. Approximate draft proposals can change acceptance and speed; qualification
must check the resulting output against a same-image serial control.

Use request-level `disable_mtp: true` for serial comparisons. Strict does not
mean serial execution. An unavailable or incompatible MTP head is a startup
error when a mode is selected.

The old `FP8_GDN=1` opt-in conflicts with the native-target contract and is
rejected in either mode. Checkpoint sampling and reasoning defaults remain in
force unless the request explicitly overrides them. Neither mode promises
identical text to an older release, another tensor-parallel topology or another
numerical reference. See the release's measured qualification and limitations.

The release profiles clear the full prefill scratch arena. The inherited
`ATLAS_GLM_ZERO_ROWS=1` shortcut is disabled because no Qwen-specific stale-byte
check qualified it across the profiles. Historical speed observations alone
do not establish its correctness.
