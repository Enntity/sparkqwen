# DaisyRose-27B calibration and evaluation token sets

> Written by the adapted `build_sets.py` with DaisyRose's tokenizer and chat template: the token data, sources, rows and counts below are DaisyRose's. Notes that name GLM token ids, `tokenization_glm5.py` or the `high` effort level are inherited from the Sage original and do not apply here (DaisyRose's efforts are xhigh, the default, medium and low).

Model `RadixArk/DaisyRose-27B-NVFP4` at revision `c4d85c5dfad123426555c22f4e24bb15381f0bdb`. Seed 20261117. Written by `build_sets.py`; do not edit by hand.

| file | rows | tokens | sha256 |
|---|---:|---:|---|
| `eval.jsonl` | 224 | 240,124 | sha256 `542d1d2f50677abff81522319035ae8f745f7eb4a6daccbf074e928c1b1ddb03` |
| `calib.jsonl` | 497 | 620,477 | sha256 `a36a1a736e557367df6b121ec2747ddfe2e55df8bfe4e86c8e68cad73ad524cb` |

Built with Python 3.12.11, tokenizers 0.23.3, jinja2 3.1.6, pyarrow 26.0.1.

Tokenizer and template files (in `cache/model/`):

- `tokenizer.json` sha256 `0997f410c57a1f4e53b09e4be8f4a172d90edd9564368fb0847030937229b9f3`
- `tokenizer_config.json` sha256 `b11349aafa7cdc6a320767cf7ceb29ed82f7eda5d65e8e0819e76f0ce947bf27`
- `chat_template.jinja` sha256 `c3cf9e34abf4f9e36c2d72165aa9c132d3e2a725b6c2586aaa3a8af9d7a81041`
- `generation_config.json` sha256 `d0d6dc40794a570ed9a66a005146ea5dc537ce11c42eb00c676bd220f6c01cf2`

## Evaluation set

| category | documents | tokens | shortest | longest |
|---|---:|---:|---:|---:|
| code | 32 | 36,864 | 1152 | 1152 |
| prose_en | 32 | 36,864 | 1152 | 1152 |
| prose_ja | 32 | 36,864 | 1152 | 1152 |
| math | 32 | 36,864 | 1152 | 1152 |
| science | 32 | 36,864 | 1152 | 1152 |
| chat_reasoning | 32 | 33,594 | 696 | 1152 |
| tool_calling | 32 | 22,210 | 601 | 903 |
| **total** | 224 | 240,124 | | |

Reasoning chat by question domain and cut:

| | documents | tokens |
|---|---:|---:|
| code, cut inside the reasoning | 5 | 5,760 |
| code, whole conversation | 6 | 5,954 |
| math, cut inside the answer | 1 | 1,152 |
| math, cut inside the reasoning | 5 | 5,760 |
| math, whole conversation | 5 | 4,533 |
| science, cut inside the answer | 1 | 1,152 |
| science, cut inside the reasoning | 4 | 4,608 |
| science, whole conversation | 5 | 4,675 |

## Calibration set

| group | target | share | category | sequences | tokens | shortest | longest |
|---|---:|---:|---|---:|---:|---:|---:|
| chat_reasoning | 30% | 29.5% | chat_reasoning | 103 | 183,174 | 799 | 2048 |
| chat | 15% | 14.5% | chat | 83 | 90,036 | 343 | 2046 |
| tool_calling | 12% | 11.7% | tool_calling | 122 | 72,356 | 386 | 951 |
| code | 15% | 15.2% | code | 79 | 94,014 | 410 | 2048 |
| prose_en + science | 10% | 10.2% | prose_en | 20 | 30,651 | 318 | 2048 |
| | | | science | 16 | 32,582 | 1862 | 2048 |
| prose_multilingual | 13% | 13.9% | prose_multilingual | 57 | 86,132 | 277 | 2048 |
| math | 5% | 5.1% | math | 17 | 31,532 | 1460 | 2027 |
| **total** | 100% | 100% | | 497 | 620,477 | | |

Reasoning chat by question domain and cut:

| | sequences | tokens |
|---|---:|---:|
| code, cut inside the answer | 4 | 8,192 |
| code, cut inside the reasoning | 10 | 20,480 |
| code, whole conversation | 20 | 32,532 |
| math, cut inside the answer | 2 | 4,096 |
| math, cut inside the reasoning | 12 | 24,576 |
| math, whole conversation | 22 | 32,186 |
| science, cut inside the answer | 9 | 18,432 |
| science, cut inside the reasoning | 5 | 10,240 |
| science, whole conversation | 19 | 32,440 |

Chat rows by `reasoning_effort` passed to the template (none = the template's default, Max):

| | sequences | tokens |
|---|---:|---:|
| chat_reasoning, none | 49 | 85,957 |
| chat_reasoning, medium | 54 | 97,217 |
| chat, none | 29 | 32,175 |
| chat, low | 31 | 31,513 |
| chat, medium | 23 | 26,348 |
| tool_calling, low | 37 | 22,734 |
| tool_calling, medium | 38 | 22,187 |
| tool_calling, none | 47 | 27,435 |

Plain multi-turn chat by cut:

| | sequences | tokens |
|---|---:|---:|
| whole conversation | 78 | 81,141 |
| trailing exchanges dropped to fit | 5 | 8,895 |

Code by language:

| | sequences | tokens |
|---|---:|---:|
| python | 7 | 8,006 |
| javascript | 9 | 7,785 |
| typescript | 7 | 7,538 |
| java | 6 | 8,148 |
| c | 4 | 7,912 |
| c++ | 6 | 7,963 |
| go | 5 | 7,986 |
| rust | 5 | 7,797 |
| c# | 6 | 7,821 |
| php | 6 | 7,734 |
| ruby | 9 | 7,717 |
| shell | 9 | 7,607 |

Other languages:

| | sequences | tokens |
|---|---:|---:|
| ja | 8 | 8,957 |
| zh | 5 | 7,877 |
| ko | 6 | 9,088 |
| es | 5 | 8,483 |
| fr | 6 | 9,346 |
| de | 4 | 8,192 |
| ru | 6 | 9,472 |
| ar | 6 | 8,508 |
| hi | 7 | 8,132 |
| pt | 4 | 8,077 |

Science by source:

| | sequences | tokens |
|---|---:|---:|
| common-pile/arxiv_papers | 8 | 16,384 |
| common-pile/pubmed | 8 | 16,198 |

Plain documents by window (whole = shorter than the window, head = first 2,048 tokens, offset = 2,048 tokens from a random line):

| | sequences | tokens |
|---|---:|---:|
| whole | 113 | 119,263 |
| head | 39 | 79,872 |
| offset | 37 | 75,776 |

## Sources

All fetched anonymously over HTTPS from `https://huggingface.co/datasets/<id>/resolve/<revision>/<file>`. Row indices are 0-based positions in the named file. The complete index lists are in `rows_used.json`; each JSONL row also carries its own `source` and `source_rows`.

### open-thoughts/OpenThoughts-114k

- revision `bd093c3994fd54d2390985b66988ddf282a55eb6`
- licence: apache-2.0
- `metadata/train-00000-of-00012.parquet` eval: 505, 580, 920
- `metadata/train-00000-of-00012.parquet` calib: 113, 123, 189, 232, 373, 463, 469, 486, 489, 519
- `metadata/train-00002-of-00012.parquet` eval: 3175, 3725, 3870
- `metadata/train-00002-of-00012.parquet` calib: 3174, 3577, 3589, 3854, 3991
- `metadata/train-00004-of-00012.parquet` eval: 7160
- `metadata/train-00004-of-00012.parquet` calib: 7024, 7228, 7313, 7747, 7848, 7936, 7944
- `metadata/train-00005-of-00012.parquet` eval: 5800
- `metadata/train-00005-of-00012.parquet` calib: 5029, 5141, 5172, 5406, 5414, 5687, 5892, 5902, 5927
- `metadata/train-00007-of-00012.parquet` eval: 2135, 2650
- `metadata/train-00007-of-00012.parquet` calib: 2257, 2847
- `metadata/train-00008-of-00012.parquet` eval: 9460
- `metadata/train-00008-of-00012.parquet` calib: 9141, 9212, 9286
- `metadata/train-00009-of-00012.parquet` eval: 6605, 6845, 8125, 8560, 8855
- `metadata/train-00009-of-00012.parquet` calib: 6177, 6308, 6377, 6383, 6484, 6509, 6588, 6663, 8112, 8143, 8186, 8754, 8898, 8981
- `metadata/train-00010-of-00012.parquet` eval: 2200, 2375, 2390, 2560, 2780, 2995
- `metadata/train-00010-of-00012.parquet` calib: 2429, 2532, 2572, 2636, 2649, 2722, 2772, 2848, 2953, 7132, 7219, 7273, 7466, 7517, 7563, 7936
- `metadata/train-00011-of-00012.parquet` eval: 5245, 5265, 5730, 6075, 6280, 7395, 7470, 7685, 7695, 7815
- `metadata/train-00011-of-00012.parquet` calib: 3181, 3622, 3934, 3966, 5016, 5093, 5117, 5166, 5202, 5441, 5512, 5544, 5602, 5623, 5648, 5912, 5987, 6228, 6326, 6432, 6481, 6506, 6782, 6788, 6919, 6929, 7061, 7106, 7111, 7308, 7339, 7361, 7379, 7583, 7651, 7909, 7932

### HuggingFaceH4/ultrachat_200k

- revision `8049631c405ae6576f93f445c6b8166f76f5505a`
- licence: mit
- `data/train_sft-00000-of-00003-a3ecf92756993583.parquet` calib: 83 rows between 0 and 35992 (list in `rows_used.json`)

### glaiveai/glaive-function-calling-v2

- revision `8862406ff857565709af3dca7fed589b84edf235` (refs/convert/parquet of main e7f4b6456019f5d8bcb991ef0dd67d8ff23221ac)
- licence: apache-2.0
- `default/train/0000.parquet` eval: 1620, 2090, 2170, 2320, 4560, 4630, 4965, 5290, 5530, 5780, 6095, 6900, 7010, 7030, 9760, 10505, 10630, 11425, 12285, 12465, 12985, 13145, 13800, 13930, 14755, 15620, 16880, 17475, 17520, 17555, 17795, 18440
- `default/train/0000.parquet` calib: 122 rows between 746 and 19956 (list in `rows_used.json`)

### codeparrot/github-code-clean

- revision `c48d40f9e70f0196f8236901ee35807f7d6c44c0`
- licence: apache-2.0 on the card; each file carries its repository licence, only mit/apache-2.0/bsd/isc/unlicense/cc0-1.0 files are used
- `data/train-00000-of-00880.parquet` eval: 105, 1770, 4710, 4875, 5820
- `data/train-00000-of-00880.parquet` calib: 396, 531, 689, 777, 799, 837, 943, 1041, 1239, 1544, 1688, 1691, 1712, 1901, 2008, 2371, 2646, 3538, 3868, 3963, 4154, 4416, 4452, 4522
- `data/train-00293-of-00880.parquet` eval: 385, 855, 965, 3260, 3920, 4710, 4845, 4860, 5655, 6285, 6655, 7985, 8055, 8785, 8825, 9950
- `data/train-00293-of-00880.parquet` calib: 53, 213, 344, 823, 928, 956, 2263, 2322, 2649, 3117, 3291, 5339, 6061, 6207, 6937, 7049, 7798, 8256, 8611, 8842, 9627, 9638, 9809
- `data/train-00586-of-00880.parquet` eval: 650, 865, 985, 1145, 3520, 6030, 6375
- `data/train-00586-of-00880.parquet` calib: 1042, 2212, 2257, 2288, 2411, 3504, 4727, 5171, 5736, 6118, 7138, 7224, 7636, 8256, 8582, 8724, 8793, 8991, 9329, 9503
- `data/train-00879-of-00880.parquet` eval: 7130, 7300, 8985, 9500
- `data/train-00879-of-00880.parquet` calib: 267, 609, 1552, 7502, 7814, 8449, 8559, 8692, 9046, 9153, 9602, 9698
- per-row licences used: mit (66); apache-2.0 (30); bsd-3-clause (12); unlicense (1); isc (1); bsd-2-clause (1)

### wikimedia/wikipedia

- revision `b04c8d1ceb2f5cd4588862100d08de323dccfbaa`
- licence: cc-by-sa-3.0 and gfdl
- `20231101.ar/train-00000-of-00007.parquet` calib: 271, 409, 994, 40064, 40228, 40247
- `20231101.de/train-00000-of-00020.parquet` calib: 114, 329, 798, 40234
- `20231101.en/train-00000-of-00041.parquet` eval: 20, 55, 320, 335, 355, 365, 390, 455, 460, 515, 555, 595, 600, 620, 630, 650, 675, 725, 805, 870, 885, 955, 985, 40040, 40130, 40175, 40485, 40540, 40670, 40700, 40860, 40910
- `20231101.en/train-00000-of-00041.parquet` calib: 93, 159, 247, 279, 311, 449, 498, 517, 554, 583, 921, 974, 983, 988, 40263, 40383, 40489, 40667, 40733, 40746
- `20231101.es/train-00000-of-00013.parquet` calib: 256, 801, 933, 40451, 40989
- `20231101.fr/train-00000-of-00017.parquet` calib: 961, 964, 40058, 40257, 40784, 40938
- `20231101.hi/train-00000-of-00002.parquet` calib: 13, 59, 84, 188, 507, 596, 989
- `20231101.ja/train-00000-of-00015.parquet` eval: 45, 75, 160, 195, 215, 270, 285, 345, 385, 405, 480, 635, 750, 945, 990, 40125, 40205, 40230, 40360, 40365, 40375, 40395, 40405, 40435, 40510, 40625, 40765, 40775, 40840, 40845, 40855, 40950
- `20231101.ja/train-00000-of-00015.parquet` calib: 246, 309, 593, 713, 776, 877, 896, 40828
- `20231101.ko/train-00000-of-00003.parquet` calib: 684, 706, 40258, 40481, 40657, 40948
- `20231101.pt/train-00000-of-00006.parquet` calib: 166, 628, 822, 40452
- `20231101.ru/train-00000-of-00021.parquet` calib: 451, 657, 40242, 40407, 40497, 40603
- `20231101.zh/train-00000-of-00006.parquet` calib: 406, 414, 959, 40076, 40689

### common-pile/arxiv_papers

- revision `963fe980c55b353980653f1a27c1dc0c8a2d7058`
- licence: no licence field on the card; the card says it holds only papers under CC BY, CC BY-SA and CC0, with the licence in each row's metadata
- `00000_arxiv-papers.jsonl.gz` eval: 25, 45, 130, 140, 215, 310, 360, 375, 380
- `00000_arxiv-papers.jsonl.gz` calib: 6, 81, 283, 362, 393
- `00012_arxiv-papers.jsonl.gz` eval: 100, 110, 125, 150, 205, 215, 250
- `00012_arxiv-papers.jsonl.gz` calib: 52, 127-128
- per-row licences used: Creative Commons - Attribution - https://creativecommons.org/licenses/by/4.0/ (12); Creative Commons - Attribution - https://creativecommons.org/licenses/by/3.0/ (11); Public Domain (1)

### common-pile/pubmed

- revision `648b8cfc93953ca0663a9c96a8d842a91b98fb64`
- licence: no licence field on the card; the card says it holds only papers under CC BY, CC BY-SA and CC0, with the licence in each row's metadata
- `data/00000_pubmedcentral.jsonl.gz` eval: 225, 235, 315, 360, 450, 500, 520, 675, 690
- `data/00000_pubmedcentral.jsonl.gz` calib: 14, 44, 74, 282, 302, 353, 433, 547
- `data/00010_pubmedcentral.jsonl.gz` eval: 65, 75, 190, 215, 225, 235, 275
- per-row licences used: Creative Commons - Attribution - https://creativecommons.org/licenses/by/4.0/ (24)

### EleutherAI/hendrycks_math

- revision `21a5633873b6a120296cce3e2df9d5550074f4a3`
- licence: mit
- `algebra/test-00000-of-00001.parquet` eval: 2, 21, 57, 61, 128, 157, 162, 183, 238, 243, 255, 317, 321, 356, 371, 442, 480, 587, 590, 647, 685, 688, 735, 763, 961, 1010, 1024, 1069, 1093, 1156, 1179
- `algebra/train-00000-of-00001.parquet` calib: 28, 57, 61, 64, 194, 230, 250, 267, 333, 338, 375, 394, 457, 491, 494, 546, 676, 769, 879, 1008, 1301, 1344, 1459, 1468, 1470, 1495, 1518, 1535, 1583, 1597, 1719
- `counting_and_probability/test-00000-of-00001.parquet` eval: 1, 10, 44, 46, 65, 79, 88, 99, 104, 108, 121, 134, 230, 255, 283, 289, 321, 324, 339, 345-346, 409, 418, 433, 437, 456, 472
- `counting_and_probability/train-00000-of-00001.parquet` calib: 9, 17, 39, 103, 137, 201, 207, 270, 409, 447, 480, 536, 549, 595, 634, 647, 685, 705, 749
- `geometry/test-00000-of-00001.parquet` eval: 8, 31, 109, 119, 145, 150, 173, 176, 270, 297, 323, 343, 379, 415, 445, 459
- `geometry/train-00000-of-00001.parquet` calib: 67, 98, 138, 281, 298, 312, 395, 413, 456, 471, 717, 777, 865
- `intermediate_algebra/test-00000-of-00001.parquet` eval: 103, 168, 349, 394, 423, 465, 488, 587, 647, 695, 701, 791, 797, 807, 836, 882
- `intermediate_algebra/train-00000-of-00001.parquet` calib: 47-48, 79, 360, 421, 688, 1092, 1154, 1172, 1284
- `number_theory/test-00000-of-00001.parquet` eval: 5, 9, 25, 52, 87, 92, 114, 161, 193, 196, 268, 270, 305, 317, 325, 383, 433, 479, 496, 511, 516
- `number_theory/train-00000-of-00001.parquet` calib: 16, 37, 43, 150, 251, 301, 502, 518, 638, 672, 691, 770, 809, 830
- `prealgebra/test-00000-of-00001.parquet` eval: 11, 17, 121, 134, 176, 262, 271, 307, 325, 328, 357, 374, 400, 467, 516, 583, 639, 680, 782, 791, 805, 862
- `prealgebra/train-00000-of-00001.parquet` calib: 70, 86, 113, 134, 179, 272, 274, 377, 419, 609, 660, 680, 801, 992, 1015, 1054, 1071, 1123, 1172
- `precalculus/test-00000-of-00001.parquet` eval: 5, 23, 63, 79, 82, 121, 193, 207, 369, 434, 483, 487, 495, 527
- `precalculus/train-00000-of-00001.parquet` calib: 307, 447, 484, 539, 548, 570, 597

## Row format

One JSON object per line:

- `id`: `eval-<category>-NNN` or `calib-<category>-NNNN`
- `category`: evaluation has `code`, `prose_en`, `prose_ja`, `math`, `science`, `chat_reasoning`,
  `tool_calling`; calibration has `chat_reasoning`, `chat`, `tool_calling`, `code`, `prose_en`,
  `science`, `prose_multilingual`, `math`
- `lang`: language code of the text (`en`, `ja`, ...); for `code` the programming language
- `source`: `<dataset id>@<revision sha>:<file>`
- `source_row`: 0-based index of the (first) source row in that file; `source_rows`: all of them
- `n_tokens`, `input_ids`: the sequence, with no prefix token (Qwen adds no BOS)
- `window` (plain documents): `whole`, `head` or `offset`
- `truncated` (chat rows): `none`, `turns` or `tokens`
- `reasoning_effort` (chat rows): `null` (xhigh), `"medium"` or `"low"` as passed to the template
- `domain` (reasoning chat): `code`, `math` or `science`
- `licence` (code and science): the licence the source gives for that row

## Deviations from the brief and things to know

Evaluation set

1. Reasoning chat is half whole, half cut. OpenThoughts reasoning traces are long: the rendered
   conversation has a median of about 5,600 tokens for math, 6,400 for code and 2,200 for science,
   and only 1 to 2 in 100 fit in 600 to 1,152 tokens. Taking only conversations that fit would have
   meant only the easiest questions. So 16 documents are whole conversations (reasoning, `</think>`,
   answer; 6 code, 5 math, 5 science) and 16 are ordinary conversations cut at 1,152 tokens (5 code,
   6 math, 5 science); most of those end inside the reasoning, a few reach `</think>` and are cut
   in the answer (counts in the table above). The `truncated` field says which is which (`none` or
   `tokens`).
2. Tool-calling documents are the long tail of Glaive. With the template's tools preamble a Glaive
   conversation has a median of about 375 tokens; only 2 to 3% reach the 600-token floor. All 32
   are whole conversations, but they are the longest ones (more turns or more tool schemas).
3. Math documents are several problems joined together. A Hendrycks MATH row (problem + solution)
   is about 250 tokens, so each document is `Problem:\n...\n\nSolution:\n...` blocks from one
   subject, joined by blank lines until the text passes 1,152 tokens, then cut. The last solution
   of each document is therefore cut short. Evaluation uses the test split and calibration the
   train split.
4. All plain evaluation documents are exactly 1,152 tokens (sources shorter than that were skipped),
   to line up with the published comparison's roughly 1,127 scored positions per document. They are
   the head of the source: code files often begin with a licence header.
5. Science is 16 arXiv papers and 16 PubMed Central papers, full text from the top.

Calibration set

6. "English prose and scientific text" (10%) is split evenly into two categories, `prose_en`
   (English Wikipedia) and `science` (half arXiv, half PubMed Central full text).
7. Reasoning chat is a third each of code, math and science questions. Because most traces are
   longer than 2,048 tokens, at most half of each domain's tokens come from conversations cut at
   2,048 (most end inside the reasoning); the rest are whole conversations, which over-represents
   short traces compared with the dataset.
8. `reasoning_effort` is varied in calibration so that all three system lines the template can emit
   are seen: reasoning chat draws from unset/`high`, plain chat and tool calling from
   unset/`high`/`low`. Unset renders as `Reasoning Effort: Max` (the template has no way to omit
   the line). Evaluation always leaves it unset. The value is in each chat row's `reasoning_effort`.
9. Plain chat (UltraChat) and tool calling (Glaive) carry no reasoning, so every assistant turn in
   them renders as `<think></think>` followed by the answer, which is what the template emits for an
   assistant turn without `reasoning_content`. Only the OpenThoughts rows have non-empty reasoning.
10. A plain chat longer than 2,048 tokens loses whole trailing user/assistant exchanges until it fits,
    rather than being cut mid-turn (`truncated` = `turns`).
11. Half of the plain documents longer than the window start at a random line of the source instead
    of at the top (`window` = `offset`); still one window per source document.
12. Math documents are joined problems as in the evaluation set, but a document stops before the
    problem that would pass 2,048 tokens, so nothing is cut.

Sources

13. Science comes from `common-pile/arxiv_papers` and `common-pile/pubmed`. Their shards are 0.3 to
    2.8 GB gzip files, so only the first 6,000,000 bytes of two shards each are fetched and the
    complete lines in them used; these are the earliest papers of each shard. Neither card has a
    licence field; both say the collection is limited to CC BY, CC BY-SA and CC0 papers and give the
    licence per row, which is copied into each row's `licence`. The arXiv text is LaTeX converted to
    plain text and carries conversion noise (footnote digits glued to words, tables of contents);
    the PubMed text is markdown with anchors such as `{#s1}`.
14. Code comes from `codeparrot/github-code-clean` (not gated, has a per-file licence column), four
    row groups from four shards. Only files whose repository licence is MIT, Apache-2.0, BSD, ISC,
    Unlicense or CC0 are used (GPL, MPL and the rest are dropped), in twelve languages with equal
    token budgets: Python, JavaScript, TypeScript, Java, C, C++, Go, Rust, C#, PHP, Ruby, Shell.
    Files under 1,500 or over 80,000 characters, under 30 lines, or with a line over 240 characters
    are dropped. The licence column is the dataset's claim about the repository; a few files carry
    a different licence in their own header.
15. Glaive is read from the Hub's parquet conversion of the dataset's single JSON file (branch
    `refs/convert/parquet`, pinned by its own sha) so that only the first 20,000 rows need fetching.
    The `SYSTEM:` text is not kept as a message: its function list becomes `tools` (OpenAI shape)
    and the template writes its own tools preamble. Each `<functioncall>` becomes a `tool_calls`
    entry with an id and each `FUNCTION RESPONSE` a `tool` message. Rows with no functions, with
    functions but no call, or that do not parse cleanly (about 7% of those with a call) are skipped.
16. OpenThoughts is read from its `metadata` config (separate problem, reasoning and solution
    columns) rather than the default config, whose assistant text wraps both in its own markers and
    whose system prompt describes that format. No system message is used. The puzzle rows are not
    used; science is the biology, physics and chemistry rows.
17. Wikipedia rows are the title, a blank line and the text. Only row groups 0 and 40 of each
    language's first shard are read (2,000 articles), which leans towards older, longer articles.
18. Row groups are fetched with HTTP range requests instead of downloading whole shards; the cache
    holds only those row groups and columns.

Both sets

19. Extra fields. `source_row` is the first source row and `source_rows` lists all of them (they
    differ only for math). Rows also carry `window`, `truncated`, `reasoning_effort`, `domain` and
    `licence` where they apply.
20. Disjointness is by construction: in every source that feeds both sets, rows whose index in the
    file is a multiple of 5 can only go to evaluation and all other rows only to calibration (math
    uses the test and train splits instead). No source row is used twice.
21. Any source text containing one of the tokenizer's 36 added-token strings (`<think>`, `[MASK]`,
    `<|user|>`, `/nothink`, ...) is skipped, so plain documents hold no control ids after the
    prefix and chat rows hold only the ones the template wrote.
22. Nothing is appended at the end of a document or conversation: no `<|endoftext|>`, no trailing
    role token, no generation prompt. A cut never ends inside a character: trailing tokens that
    would leave half a UTF-8 character are dropped, so a cut row can be up to three tokens short of
    the limit.
23. `<think>`, `</think>`, `<tool_call>`, `<arg_key>`, `<tool_response>` and their closing forms are
    single ids, but tokenizer.json marks them `special: false` (only `<|endoftext|>` to
    `<|end_of_transcription|>`, ids 154820 to 154837, are `special: true`). Decoding with
    `skip_special_tokens=True` keeps them.

Template rendering

24. The template is rendered with jinja2 set up as transformers does it: an
    `ImmutableSandboxedEnvironment` with `trim_blocks`, `lstrip_blocks`, the `loopcontrols`
    extension (the template uses `break`), transformers' `tojson` (plain `json.dumps`, no HTML
    escaping, `ensure_ascii=False`), `raise_exception` and `strftime_now`; called with `messages`,
    `tools`, `documents=None`, `add_generation_prompt=False`, `eos_token`, `pad_token` and
    `reasoning_effort` when set; tokenized with `add_special_tokens=False`. `test_sets.py` compares
    this with `PreTrainedTokenizerFast.apply_chat_template` on four fixed cases and on every chat
    row saved in `cache/render_samples.jsonl` (all 64 evaluation chat rows and 40 calibration rows
    per chat category).
25. Not checked: the model repo also ships `tokenization_glm5.py` (the `Glm5Tokenizer` named in
    `auto_map`), `processing_glm5.py` and a vLLM patch about tool and media ordering. They were not
    downloaded, read or run. The cross-check above uses the stock fast tokenizer class with the
    shipped `tokenizer.json` and `chat_template.jinja`; if the custom class changes how text is
    encoded or how the template is applied, these sets would not show it.
