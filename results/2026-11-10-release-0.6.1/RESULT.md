<!-- SPDX-License-Identifier: AGPL-3.0-only -->
# SparkQwen 0.6.1: release checks

2026-11-10. SparkQwen 0.6.1 is a patch release for the Qwen3.8-27B candidate:
one engine fix, for a request that joins two or more decoding requests
([what it fixes](../2026-11-10-27b-mixed-forward/RESULT.md)). This records
what was checked for each of the two images, and what was not.

**The 27B image was run on one Spark: exactness holds alone, eight at a time
and for a long request joining two decoding requests. The Flash-Next image
carries the same engine binary as 0.6.0, byte for byte, and was not run on
GPUs.**

## Identity

Both images are built from product commit
`1810c31c7f63d89f886a6cab27d7096014e2f3fa`, install tree
`b2995a9621e2f748f04ac0ced8e6dd6f5c0488f3`. [`manifest.json`](manifest.json)
has every value below in one place.

| | Qwen3.8-Flash-Next | Qwen3.8-27B |
|---|---|---|
| Tags | `b2995a9621e2`, `0.6.1` | `b2995a9621e2-27b`, `0.6.1-27b` |
| Registry digest | `sha256:2c880892baefcea477df3a7157b877a944fa3e9cbab27439568950f1e244110f` | `sha256:5d5dddde62bee256fa60d928e698c5cd5ff2d65ec2c905caf22ae94a28f2ba23` |
| arm64 manifest | `sha256:98d7b757f2fb03b8f0e8966e61b4f04d796431aecb516b15e4cfc4a163f52462` | `sha256:9683363da6765e69a042cfa7fe8edba179a0803c952e9a421b775a90b9ab7ae0` |
| Atlas commit | `5f79b46ba7b0e8b14f8b2966cca9e2546f18560d` (Enntity/atlas `spark`) | `32e4295ca8ae243b10341cd8cde2c700f96dc5f2` (Enntity/atlas `q27/conc`) |
| Atlas tree | `38c21decf794bd9921081d022a6720a933431eaf` | `3f95364330e6eff4dfe9324acf06937892d70399` |
| Engine binary | `c719a0b1a5808511d780b65a2b3021336dbf702ff3bfe1591f7da01c379cd9a8` | `69cb8d313da84e78f61c265de18b5c24aef402b261c06a905c9f173494a2ca57` |

The four tags pull anonymously and resolve to these digests. The registry's
answers for the two install-tree tags are
[here](raw/registry-b2995a9621e2.json) and
[here](raw/registry-b2995a9621e2-27b.json).

## Both images

Each build ran the engine's workspace tests and Clippy inside the image build,
from a checkout of the pinned commit: 8,477 passed, 0 failed, 300 ignored for
Flash-Next and 8,580 passed, 0 failed, 304 ignored for the 27B, with the
skips the Dockerfile lists
([Flash-Next log](raw/image-build-flash-next.log.gz),
[27B log](raw/image-build-27b.log.gz)). The 27B count is three more than
0.6.0's: the fix's own scheduler tests. The install tests (85) pass on the
product commit.

## Flash-Next: the same engine binary as 0.6.0

0.6.1 rebuilds the Flash-Next image only because the 27B pin and the version
changed `install/`, and the image tag is that tree's hash. Against the 0.6.0
image
(`sha256:02a0ffaed9e4c51c6eedc0d1309de1dc8c58f0e41075d1fda80efa4e0b447fad`):

- **Engine binary.** The same file: same size, same SHA-256, all 34 ELF
  sections identical ([sections](raw/elf_sections.out),
  [script](raw/elf_sections.py)).
- **Other files.** Under `/opt/atlas` and `/usr/local/bin` only
  `release.json` differs ([diff](raw/files.diff)). The launcher, profiles,
  checkpoint manifest and chat templates have the same hashes. The second
  entry in that diff is the engine binary itself, which the 0.6.0 listing did
  not include.
- **System packages.** No difference ([diff](raw/dpkg.diff)).

So the qualification that stands for Flash-Next is still
[0.5.1's](https://github.com/Enntity/sparkqwen/releases/tag/v0.5.1), through
[0.6.0's identity checks](../2026-11-10-release-0.6.0/RESULT.md). This image
was not started on a pair.

## Qwen3.8-27B: this image on one Spark

The released 27B image with the default `27b` profile, started by
[`27b-run_rel.sh`](raw/27b-run_rel.sh) with nothing mounted over it
([log](raw/27b-image-check.log)). Temperature 0.

| Check | Result |
|---|---|
| Version and install tree in the running container | 0.6.1, `b2995a9621e2` |
| Short code probe, thinking off, two runs | 70.4, 70.2 tok/s |
| Short thinking probe, two runs | 72.7, 72.8 tok/s |
| 8 prompts × thinking on/off, 250 tokens: speculative vs serial | 16 of 16 identical |
| The same 16 cells, eight requests at a time, vs serial | 16 of 16 identical |
| 21,368-token request alone: speculative vs serial | identical |
| The same request joining two decoding requests, vs serial | identical |
| That request: tokens per step, decode, time to first token | 3.19, 21.75 tok/s, 0.46 s |
| The two decoding requests beside it: decode, text vs serial | 34.08 and 31.57 tok/s, identical |
| Mixed forwards and drafter failures in the server log | 0 and 0 |

The 16 short cells give the same text hashes as on 0.6.0. The join check is
the one described in
[the before and after](../2026-11-10-27b-mixed-forward/RESULT.md), with the
same driver (`mix.py`); its rows for this image are
[here](raw/27b-join-requests.json). The probe and the 16-cell drivers are
`decode_probe.py` and `bx.py` from
[the shared-scan receipts](../2026-11-10-27b-shared-scan/raw/).

## Not checked

- Flash-Next 0.6.1 has no GPU run. Its case rests on the identities above.
- The 27B is a candidate. It has no qualification run and no RigMark run.
- The 210K-token turns measured for 0.6.0 were not repeated on this image.
- One run of the join check, with two decoding requests. Wider batches,
  sampled decoding and the `27b-max` and `27b-saver` profiles were not run.
- The checks above started the image directly. The same image was then
  deployed through LLooM on that Spark, where it answered a request; no
  further measurement was taken there.

## Receipts

[`SHA256SUMS`](SHA256SUMS) covers this folder. The build logs are the image
builds' own output, compressed. `27b-image-check.log` is the runner's output;
the request rows carry a SHA-256 of each response's text instead of the text.
