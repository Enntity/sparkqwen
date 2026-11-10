<!-- SPDX-License-Identifier: AGPL-3.0-only -->
# SparkQwen 0.6.0: release checks

2026-11-10. SparkQwen 0.6.0 adds Qwen3.8-27B on one DGX Spark, a candidate,
behind `--model 27b`, beside Qwen3.8-Flash-Next on two. This records what was
checked for each of the two images, and what was not.

**Flash-Next runs the engine 0.5.1 ran: the same Atlas commit, and an engine
binary whose loaded sections are byte-identical. It was not run on GPUs again.
The 27B image was checked live on one Spark; it is a candidate with no
qualification run.**

## Identity

Both images are built from product commit
`85ac2ef1e849a97802e570be492d1e4b8951df64`, install tree
`f6bb0a3cd40d5f14f599431399f87f1e8f27973b`. [`manifest.json`](manifest.json)
has every value below in one place.

| | Qwen3.8-Flash-Next | Qwen3.8-27B |
|---|---|---|
| Tags | `f6bb0a3cd40d`, `0.6.0` | `f6bb0a3cd40d-27b`, `0.6.0-27b` |
| Registry digest | `sha256:02a0ffaed9e4c51c6eedc0d1309de1dc8c58f0e41075d1fda80efa4e0b447fad` | `sha256:06bc69b4dfc3cb4d433293d2794bfab6c5bad33a48651ac49558173f6d8dc403` |
| arm64 manifest | `sha256:e00f5542b7c68464ae04b46f1120c400c63f88f14c7356fad0bb3fe0837ce8e3` | `sha256:6945983799a4f9e722b32b308d28ec733fb432ed893b45bec18127ec86d333a3` |
| Atlas commit | `5f79b46ba7b0e8b14f8b2966cca9e2546f18560d` (Enntity/atlas `spark`) | `c125bf9a87db35033939342815e239d8a36541d9` (Enntity/atlas `q27/conc`) |
| Atlas tree | `38c21decf794bd9921081d022a6720a933431eaf` | `372e03793dc82d3aab0a7a89f6c8380b69761ab7` |
| Engine binary | `c719a0b1a5808511d780b65a2b3021336dbf702ff3bfe1591f7da01c379cd9a8` | `0194e72732fd199ea03623ba9e4ee6f15acea95d1e03ed57660774d06b7330e0` |

The four tags pull anonymously and resolve to these digests. The registry's
answers for the two install-tree tags are
[here](raw/registry-f6bb0a3cd40d.json) and
[here](raw/registry-f6bb0a3cd40d-27b.json).

## Both images

Each build ran the engine's workspace tests and Clippy inside the image build,
from a checkout of the pinned commit: 8,477 passed, 0 failed, 300 ignored for
Flash-Next and 8,577 passed, 0 failed, 304 ignored for the 27B, with the
skips the Dockerfile lists
([Flash-Next log](raw/image-build-flash-next.log.gz),
[27B log](raw/image-build-27b.log.gz)). The install tests (85) and the rest of
the static workflow pass on the product commit.

## Flash-Next: the same engine as 0.5.1

0.6.0 rebuilds the Flash-Next image only because the 27B variant changed
`install/`, and the image tag is that tree's hash. Against the 0.5.1 image
(`sha256:37272dc6dcb3d1c6d4b8027b8876edf9ba36b1988d85ea6accde22848d5e11e7`):

- **Engine binary.** Same size (99,950,488 bytes). All 32 other ELF sections
  are byte-identical, including `.text`, `.rodata`, `.data` and the embedded
  GPU kernels (`.nv_fatbin`); only `.symtab` and `.strtab`, which the loader
  does not map, differ ([sections](raw/elf_sections.out),
  [script](raw/elf_sections.py)). The file hashes therefore differ.
- **Launcher.** `serve.py` changed to add the 27B path. For all 8 Flash-Next
  profiles, both modes, both ranks and 8 sets of operator overrides, the
  0.5.1 and 0.6.0 launchers return the same engine arguments and environment:
  256 cases, 0 differences ([output](raw/launcher_equiv.out),
  [script](raw/launcher_equiv.py)). The profile files are unchanged.
- **Other files.** Under `/opt/atlas` and `/usr/local/bin` the image adds the
  three 27B profiles and changes `release.json` and `serve.py`; everything
  else, the checkpoint manifest and chat templates included, has the same
  hash ([diff](raw/files.diff)).
- **System packages.** Four Ubuntu packages are newer, from the build-time
  `apt-get`: `ca-certificates`, `libbrotli1`, `libglib2.0-0t64` and `tzdata`
  ([diff](raw/dpkg.diff)).

So the qualification that stands for Flash-Next is
[0.5.1's](https://github.com/Enntity/sparkqwen/releases/tag/v0.5.1). This
image was not started on a pair, and none of 0.5.1's measurements were
repeated on it.

## Qwen3.8-27B: live check of this image

The released 27B image, serving on one DGX Spark with the default `27b`
profile ([log](raw/27b-live-check.log), [driver](raw/27b-live_check.sh),
[per-request rows](raw/27b-live-requests.json)):

| Check | Result |
|---|---|
| Version and install tree in the running container | 0.6.0, `f6bb0a3cd40d` |
| `decode_probe.py`, code, thinking off | 70.5, 70.3 tok/s |
| `decode_probe.py`, thinking on | 72.8, 72.8 tok/s |
| Speculative text against serial, 8 prompts × thinking on/off, 250 tokens | 16 of 16 identical |
| The same eight at a time | 16 of 16 identical |
| Real agentic turns at 210,382 / 210,882 / 211,437 prompt tokens, greedy | 38.3, 32.9, 19.8 tok/s |
| Serial decode at 211,437 prompt tokens | 6.8 tok/s |
| Serial against speculative at 211,437 tokens, same start, 250 tokens | identical |
| Step time on those turns | 172–179 ms |

These match the before-and-after measured with the engine binary swapped into
the previous image
([shared-scan result](../2026-11-10-27b-shared-scan/RESULT.md)), where the
same turns ran at 18.5, 15.4 and 9.5–10.3 tok/s without the change.

## Limits

- Flash-Next 0.6.0 has no GPU run. Its case rests on the identities above.
- The 27B is a candidate. This is one Spark, one profile, one session's
  turns, greedy; it is not a benchmark run under the
  [shared method](../../docs/BENCHMARKS.md), and `27b-max` and `27b-saver`
  were not started on this image.
- The long turns come from a private agent session; the request rows keep
  counts and timings and replace the texts with their SHA-256.
- The limits in the [shared-scan result](../2026-11-10-27b-shared-scan/RESULT.md)
  apply here too, including that greedy text at about 210K tokens depends on
  which checkpoint the prefill restored from.
- The engine checks named in VERSIONING.md beyond the image build (hygiene
  gates, hardware benchmark gates) were not run for this release.

`sha256sum -c SHA256SUMS` covers every file here.
