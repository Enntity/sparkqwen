Performance comparison. Deltas are candidate minus baseline; ranges are observed minimum–maximum. No pass threshold or statistical significance claim is applied.
Every numeric workload leaf and repetition is retained in numeric-ledger.jsonl. Identity differences and incomplete evidence are in report.json; inventory.json records source hashes.

Qwen published matrix — Same-pair release-recipe comparison; identity changes require review.

Identity differences: 201. Review image, profile, context, sampling, clocks and host attribution before drawing conclusions.

| Cell / metric | Baseline median [range]; n | Candidate median [range]; n | Δ | Δ% | Review |
| --- | ---: | ---: | ---: | ---: | --- |
| c1-16k/requests[0]/decode_tok_s | 89.467 [89.467–89.467]; 1 | 105.476 [105.476–105.476]; 1 | 16.009 | 17.8938 | n≤2; no noise or causality inference; identity differences: review |
| c1-16k/requests[0]/effective_prefill_tok_s | 4159.36 [4159.36–4159.36]; 1 | 4488.13 [4488.13–4488.13]; 1 | 328.772 | 7.90439 | n≤2; no noise or causality inference; identity differences: review |
| c1-16k/requests[0]/elapsed_s | 8.39881 [8.39881–8.39881]; 1 | 7.43337 [7.43337–7.43337]; 1 | -0.965446 | -11.495 | n≤2; no noise or causality inference; identity differences: review |
| c1-16k/requests[0]/inter_event_gap_p95_s | 0.0584712 [0.0584712–0.0584712]; 1 | 0.0636303 [0.0636303–0.0636303]; 1 | 0.00515911 | 8.82334 | slower: review; n≤2; no noise or causality inference; identity differences: review |
| c1-16k/requests[0]/max_inter_event_gap_s | 0.0650568 [0.0650568–0.0650568]; 1 | 0.0691195 [0.0691195–0.0691195]; 1 | 0.00406269 | 6.24484 | slower: review; n≤2; no noise or causality inference; identity differences: review |
| c1-16k/requests[0]/ttft_s | 3.93907 [3.93907–3.93907]; 1 | 3.65052 [3.65052–3.65052]; 1 | -0.288551 | -7.32536 | n≤2; no noise or causality inference; identity differences: review |
| c1-16k/summary/aggregate_decode_tok_s | 89.467 [89.467–89.467]; 1 | 105.476 [105.476–105.476]; 1 | 16.009 | 17.8938 | harness summary; n counts summaries, not requests; identity differences: review |
| c1-16k/summary/aggregate_effective_prefill_tok_s | 4159.36 [4159.36–4159.36]; 1 | 4488.13 [4488.13–4488.13]; 1 | 328.772 | 7.90439 | harness summary; n counts summaries, not requests; identity differences: review |
| c1-16k/summary/decode_tok_s_p50 | 89.467 [89.467–89.467]; 1 | 105.476 [105.476–105.476]; 1 | 16.009 | 17.8938 | harness summary; n counts summaries, not requests; identity differences: review |
| c1-16k/summary/decode_tok_s_sum | 89.467 [89.467–89.467]; 1 | 105.476 [105.476–105.476]; 1 | 16.009 | 17.8938 | harness summary; n counts summaries, not requests; identity differences: review |
| c1-16k/summary/effective_prefill_tok_s_p50 | 4159.36 [4159.36–4159.36]; 1 | 4488.13 [4488.13–4488.13]; 1 | 328.772 | 7.90439 | harness summary; n counts summaries, not requests; identity differences: review |
| c1-16k/summary/ttft_p50_s | 3.93907 [3.93907–3.93907]; 1 | 3.65052 [3.65052–3.65052]; 1 | -0.288551 | -7.32536 | harness summary; n counts summaries, not requests; identity differences: review |
| c1-16k/summary/ttft_p95_s | 3.93907 [3.93907–3.93907]; 1 | 3.65052 [3.65052–3.65052]; 1 | -0.288551 | -7.32536 | harness summary; n counts summaries, not requests; identity differences: review |
| c1-16k/summary/wall_s | 8.39939 [8.39939–8.39939]; 1 | 7.43423 [7.43423–7.43423]; 1 | -0.965166 | -11.4909 | harness summary; n counts summaries, not requests; identity differences: review |
| c1-32k/requests[0]/decode_tok_s | 103.882 [103.882–103.882]; 1 | 101.145 [101.145–101.145]; 1 | -2.73745 | -2.63514 | slower: review; n≤2; no noise or causality inference; identity differences: review |
| c1-32k/requests[0]/effective_prefill_tok_s | 4122.39 [4122.39–4122.39]; 1 | 4426.12 [4426.12–4426.12]; 1 | 303.732 | 7.36788 | n≤2; no noise or causality inference; identity differences: review |
| c1-32k/requests[0]/elapsed_s | 11.7897 [11.7897–11.7897]; 1 | 11.3482 [11.3482–11.3482]; 1 | -0.441516 | -3.74494 | n≤2; no noise or causality inference; identity differences: review |
| c1-32k/requests[0]/inter_event_gap_p95_s | 0.0578614 [0.0578614–0.0578614]; 1 | 0.0599911 [0.0599911–0.0599911]; 1 | 0.00212968 | 3.68067 | slower: review; n≤2; no noise or causality inference; identity differences: review |
| c1-32k/requests[0]/max_inter_event_gap_s | 0.0629245 [0.0629245–0.0629245]; 1 | 0.064217 [0.064217–0.064217]; 1 | 0.0012925 | 2.05404 | slower: review; n≤2; no noise or causality inference; identity differences: review |
| c1-32k/requests[0]/ttft_s | 7.94879 [7.94879–7.94879]; 1 | 7.40332 [7.40332–7.40332]; 1 | -0.545468 | -6.86227 | n≤2; no noise or causality inference; identity differences: review |
| c1-32k/summary/aggregate_decode_tok_s | 103.882 [103.882–103.882]; 1 | 101.145 [101.145–101.145]; 1 | -2.73745 | -2.63514 | slower: review; harness summary; n counts summaries, not requests; identity differences: review |
| c1-32k/summary/aggregate_effective_prefill_tok_s | 4122.39 [4122.39–4122.39]; 1 | 4426.12 [4426.12–4426.12]; 1 | 303.732 | 7.36788 | harness summary; n counts summaries, not requests; identity differences: review |
| c1-32k/summary/decode_tok_s_p50 | 103.882 [103.882–103.882]; 1 | 101.145 [101.145–101.145]; 1 | -2.73745 | -2.63514 | slower: review; harness summary; n counts summaries, not requests; identity differences: review |
| c1-32k/summary/decode_tok_s_sum | 103.882 [103.882–103.882]; 1 | 101.145 [101.145–101.145]; 1 | -2.73745 | -2.63514 | slower: review; harness summary; n counts summaries, not requests; identity differences: review |
| c1-32k/summary/effective_prefill_tok_s_p50 | 4122.39 [4122.39–4122.39]; 1 | 4426.12 [4426.12–4426.12]; 1 | 303.732 | 7.36788 | harness summary; n counts summaries, not requests; identity differences: review |
| c1-32k/summary/ttft_p50_s | 7.94879 [7.94879–7.94879]; 1 | 7.40332 [7.40332–7.40332]; 1 | -0.545468 | -6.86227 | harness summary; n counts summaries, not requests; identity differences: review |
| c1-32k/summary/ttft_p95_s | 7.94879 [7.94879–7.94879]; 1 | 7.40332 [7.40332–7.40332]; 1 | -0.545468 | -6.86227 | harness summary; n counts summaries, not requests; identity differences: review |
| c1-32k/summary/wall_s | 11.7908 [11.7908–11.7908]; 1 | 11.3495 [11.3495–11.3495]; 1 | -0.441377 | -3.74339 | harness summary; n counts summaries, not requests; identity differences: review |
| c2-16k/requests[0]/decode_tok_s | 42.5633 [42.5633–42.5633]; 1 | 44.2983 [44.2983–44.2983]; 1 | 1.73502 | 4.07633 | n≤2; no noise or causality inference; identity differences: review |
| c2-16k/requests[0]/effective_prefill_tok_s | 4175.4 [4175.4–4175.4]; 1 | 4508.81 [4508.81–4508.81]; 1 | 333.411 | 7.98513 | n≤2; no noise or causality inference; identity differences: review |
| c2-16k/requests[0]/elapsed_s | 13.2982 [13.2982–13.2982]; 1 | 12.6409 [12.6409–12.6409]; 1 | -0.657321 | -4.94293 | n≤2; no noise or causality inference; identity differences: review |
| c2-16k/requests[0]/inter_event_gap_p95_s | 0.0652279 [0.0652279–0.0652279]; 1 | 0.0647122 [0.0647122–0.0647122]; 1 | -0.000515779 | -0.790733 | n≤2; no noise or causality inference; identity differences: review |
| c2-16k/requests[0]/max_inter_event_gap_s | 3.96129 [3.96129–3.96129]; 1 | 3.67492 [3.67492–3.67492]; 1 | -0.286366 | -7.22912 | n≤2; no noise or causality inference; identity differences: review |
| c2-16k/requests[0]/ttft_s | 3.92394 [3.92394–3.92394]; 1 | 3.63378 [3.63378–3.63378]; 1 | -0.290162 | -7.39466 | n≤2; no noise or causality inference; identity differences: review |
| c2-16k/requests[1]/decode_tok_s | 64.3237 [64.3237–64.3237]; 1 | 72.4111 [72.4111–72.4111]; 1 | 8.08743 | 12.573 | n≤2; no noise or causality inference; identity differences: review |
| c2-16k/requests[1]/effective_prefill_tok_s | 2384.73 [2384.73–2384.73]; 1 | 2603.72 [2603.72–2603.72]; 1 | 218.99 | 9.18299 | n≤2; no noise or causality inference; identity differences: review |
| c2-16k/requests[1]/elapsed_s | 13.0734 [13.0734–13.0734]; 1 | 11.8027 [11.8027–11.8027]; 1 | -1.27064 | -9.71931 | n≤2; no noise or causality inference; identity differences: review |
| c2-16k/requests[1]/inter_event_gap_p95_s | 0.065 [0.065–0.065]; 1 | 0.0646868 [0.0646868–0.0646868]; 1 | -0.00031317 | -0.4818 | n≤2; no noise or causality inference; identity differences: review |
| c2-16k/requests[1]/max_inter_event_gap_s | 0.0691162 [0.0691162–0.0691162]; 1 | 0.069725 [0.069725–0.069725]; 1 | 0.00060879 | 0.880821 | slower: review; n≤2; no noise or causality inference; identity differences: review |
| c2-16k/requests[1]/ttft_s | 6.87037 [6.87037–6.87037]; 1 | 6.29253 [6.29253–6.29253]; 1 | -0.577842 | -8.41064 | n≤2; no noise or causality inference; identity differences: review |
| c2-16k/summary/aggregate_decode_tok_s | 78.6285 [78.6285–78.6285]; 1 | 87.0318 [87.0318–87.0318]; 1 | 8.40338 | 10.6875 | harness summary; n counts summaries, not requests; identity differences: review |
| c2-16k/summary/aggregate_effective_prefill_tok_s | 4163.7 [4163.7–4163.7]; 1 | 4493.3 [4493.3–4493.3]; 1 | 329.608 | 7.91622 | harness summary; n counts summaries, not requests; identity differences: review |
| c2-16k/summary/decode_tok_s_p50 | 53.4435 [53.4435–53.4435]; 1 | 58.3547 [58.3547–58.3547]; 1 | 4.91123 | 9.18957 | harness summary; n counts summaries, not requests; identity differences: review |
| c2-16k/summary/decode_tok_s_sum | 106.887 [106.887–106.887]; 1 | 116.709 [116.709–116.709]; 1 | 9.82245 | 9.18957 | harness summary; n counts summaries, not requests; identity differences: review |
| c2-16k/summary/effective_prefill_tok_s_p50 | 3280.06 [3280.06–3280.06]; 1 | 3556.26 [3556.26–3556.26]; 1 | 276.2 | 8.42057 | harness summary; n counts summaries, not requests; identity differences: review |
| c2-16k/summary/ttft_p50_s | 5.39716 [5.39716–5.39716]; 1 | 4.96315 [4.96315–4.96315]; 1 | -0.434002 | -8.04131 | harness summary; n counts summaries, not requests; identity differences: review |
| c2-16k/summary/ttft_p95_s | 6.87037 [6.87037–6.87037]; 1 | 6.29253 [6.29253–6.29253]; 1 | -0.577842 | -8.41064 | harness summary; n counts summaries, not requests; identity differences: review |
| c2-16k/summary/wall_s | 14.0743 [14.0743–14.0743]; 1 | 12.8043 [12.8043–12.8043]; 1 | -1.27 | -9.0235 | harness summary; n counts summaries, not requests; identity differences: review |
| c2-32k/requests[0]/decode_tok_s | 29.549 [29.549–29.549]; 1 | 30.7457 [30.7457–30.7457]; 1 | 1.19677 | 4.05012 | n≤2; no noise or causality inference; identity differences: review |
| c2-32k/requests[0]/effective_prefill_tok_s | 4112.81 [4112.81–4112.81]; 1 | 4437.22 [4437.22–4437.22]; 1 | 324.411 | 7.88782 | n≤2; no noise or causality inference; identity differences: review |
| c2-32k/requests[0]/elapsed_s | 21.4703 [21.4703–21.4703]; 1 | 20.3622 [20.3622–20.3622]; 1 | -1.1081 | -5.16108 | n≤2; no noise or causality inference; identity differences: review |
| c2-32k/requests[0]/inter_event_gap_p95_s | 0.064895 [0.064895–0.064895]; 1 | 0.0643012 [0.0643012–0.0643012]; 1 | -0.000593861 | -0.91511 | n≤2; no noise or causality inference; identity differences: review |
| c2-32k/requests[0]/max_inter_event_gap_s | 4.15217 [4.15217–4.15217]; 1 | 3.85693 [3.85693–3.85693]; 1 | -0.295244 | -7.11059 | n≤2; no noise or causality inference; identity differences: review |
| c2-32k/requests[0]/ttft_s | 7.9673 [7.9673–7.9673]; 1 | 7.3848 [7.3848–7.3848]; 1 | -0.582499 | -7.31113 | n≤2; no noise or causality inference; identity differences: review |
| c2-32k/requests[1]/decode_tok_s | 65.8349 [65.8349–65.8349]; 1 | 70.4293 [70.4293–70.4293]; 1 | 4.59439 | 6.97865 | n≤2; no noise or causality inference; identity differences: review |
| c2-32k/requests[1]/effective_prefill_tok_s | 2188.29 [2188.29–2188.29]; 1 | 2373.4 [2373.4–2373.4]; 1 | 185.117 | 8.45946 | n≤2; no noise or causality inference; identity differences: review |
| c2-32k/requests[1]/elapsed_s | 21.0349 [21.0349–21.0349]; 1 | 19.4716 [19.4716–19.4716]; 1 | -1.5633 | -7.43194 | n≤2; no noise or causality inference; identity differences: review |
| c2-32k/requests[1]/inter_event_gap_p95_s | 0.0647515 [0.0647515–0.0647515]; 1 | 0.0642821 [0.0642821–0.0642821]; 1 | -0.000469412 | -0.724944 | n≤2; no noise or causality inference; identity differences: review |
| c2-32k/requests[1]/max_inter_event_gap_s | 0.0683445 [0.0683445–0.0683445]; 1 | 0.0688511 [0.0688511–0.0688511]; 1 | 0.000506663 | 0.741337 | slower: review; n≤2; no noise or causality inference; identity differences: review |
| c2-32k/requests[1]/ttft_s | 14.9743 [14.9743–14.9743]; 1 | 13.8063 [13.8063–13.8063]; 1 | -1.16794 | -7.79966 | n≤2; no noise or causality inference; identity differences: review |
| c2-32k/summary/aggregate_decode_tok_s | 56.7259 [56.7259–56.7259]; 1 | 60.978 [60.978–60.978]; 1 | 4.25205 | 7.49578 | harness summary; n counts summaries, not requests; identity differences: review |
| c2-32k/summary/aggregate_effective_prefill_tok_s | 4102.58 [4102.58–4102.58]; 1 | 4426.24 [4426.24–4426.24]; 1 | 323.66 | 7.88918 | harness summary; n counts summaries, not requests; identity differences: review |
| c2-32k/summary/decode_tok_s_p50 | 47.6919 [47.6919–47.6919]; 1 | 50.5875 [50.5875–50.5875]; 1 | 2.89558 | 6.07142 | harness summary; n counts summaries, not requests; identity differences: review |
| c2-32k/summary/decode_tok_s_sum | 95.3839 [95.3839–95.3839]; 1 | 101.175 [101.175–101.175]; 1 | 5.79116 | 6.07142 | harness summary; n counts summaries, not requests; identity differences: review |
| c2-32k/summary/effective_prefill_tok_s_p50 | 3150.55 [3150.55–3150.55]; 1 | 3405.31 [3405.31–3405.31]; 1 | 254.764 | 8.08634 | harness summary; n counts summaries, not requests; identity differences: review |
| c2-32k/summary/ttft_p50_s | 11.4708 [11.4708–11.4708]; 1 | 10.5956 [10.5956–10.5956]; 1 | -0.87522 | -7.63 | harness summary; n counts summaries, not requests; identity differences: review |
| c2-32k/summary/ttft_p95_s | 14.9743 [14.9743–14.9743]; 1 | 13.8063 [13.8063–13.8063]; 1 | -1.16794 | -7.79966 | harness summary; n counts summaries, not requests; identity differences: review |
| c2-32k/summary/wall_s | 22.0361 [22.0361–22.0361]; 1 | 20.4722 [20.4722–20.4722]; 1 | -1.5639 | -7.097 | harness summary; n counts summaries, not requests; identity differences: review |
| c4-16k/requests[0]/decode_tok_s | 20.3848 [20.3848–20.3848]; 1 | 21.3436 [21.3436–21.3436]; 1 | 0.958755 | 4.70328 | n≤2; no noise or causality inference; identity differences: review |
| c4-16k/requests[0]/effective_prefill_tok_s | 4170.15 [4170.15–4170.15]; 1 | 4505.73 [4505.73–4505.73]; 1 | 335.573 | 8.04702 | n≤2; no noise or causality inference; identity differences: review |
| c4-16k/requests[0]/elapsed_s | 23.5023 [23.5023–23.5023]; 1 | 22.3304 [22.3304–22.3304]; 1 | -1.17185 | -4.98611 | n≤2; no noise or causality inference; identity differences: review |
| c4-16k/requests[0]/inter_event_gap_p95_s | 0.0771777 [0.0771777–0.0771777]; 1 | 0.0774571 [0.0774571–0.0774571]; 1 | 0.000279447 | 0.362083 | slower: review; n≤2; no noise or causality inference; identity differences: review |
| c4-16k/requests[0]/max_inter_event_gap_s | 11.8296 [11.8296–11.8296]; 1 | 10.9308 [10.9308–10.9308]; 1 | -0.898781 | -7.59776 | n≤2; no noise or causality inference; identity differences: review |
| c4-16k/requests[0]/ttft_s | 3.92887 [3.92887–3.92887]; 1 | 3.63626 [3.63626–3.63626]; 1 | -0.292611 | -7.4477 | n≤2; no noise or causality inference; identity differences: review |
| c4-16k/requests[1]/decode_tok_s | 24.2084 [24.2084–24.2084]; 1 | 25.6152 [25.6152–25.6152]; 1 | 1.40681 | 5.81127 | n≤2; no noise or causality inference; identity differences: review |
| c4-16k/requests[1]/effective_prefill_tok_s | 2378.7 [2378.7–2378.7]; 1 | 2602.51 [2602.51–2602.51]; 1 | 223.809 | 9.4089 | n≤2; no noise or causality inference; identity differences: review |
| c4-16k/requests[1]/elapsed_s | 23.3697 [23.3697–23.3697]; 1 | 21.8722 [21.8722–21.8722]; 1 | -1.49754 | -6.40803 | n≤2; no noise or causality inference; identity differences: review |
| c4-16k/requests[1]/inter_event_gap_p95_s | 0.0774057 [0.0774057–0.0774057]; 1 | 0.0777026 [0.0777026–0.0777026]; 1 | 0.000296945 | 0.383622 | slower: review; n≤2; no noise or causality inference; identity differences: review |
| c4-16k/requests[1]/max_inter_event_gap_s | 7.90332 [7.90332–7.90332]; 1 | 7.30583 [7.30583–7.30583]; 1 | -0.597492 | -7.56002 | n≤2; no noise or causality inference; identity differences: review |
| c4-16k/requests[1]/ttft_s | 6.8878 [6.8878–6.8878]; 1 | 6.29547 [6.29547–6.29547]; 1 | -0.592334 | -8.59976 | n≤2; no noise or causality inference; identity differences: review |
| c4-16k/requests[2]/decode_tok_s | 34.3698 [34.3698–34.3698]; 1 | 34.7253 [34.7253–34.7253]; 1 | 0.355471 | 1.03425 | n≤2; no noise or causality inference; identity differences: review |
| c4-16k/requests[2]/effective_prefill_tok_s | 1669.73 [1669.73–1669.73]; 1 | 1836.72 [1836.72–1836.72]; 1 | 166.994 | 10.0012 | n≤2; no noise or causality inference; identity differences: review |
| c4-16k/requests[2]/elapsed_s | 21.4214 [21.4214–21.4214]; 1 | 20.4104 [20.4104–20.4104]; 1 | -1.01097 | -4.71945 | n≤2; no noise or causality inference; identity differences: review |
| c4-16k/requests[2]/inter_event_gap_p95_s | 0.0772819 [0.0772819–0.0772819]; 1 | 0.0778205 [0.0778205–0.0778205]; 1 | 0.00053862 | 0.696955 | slower: review; n≤2; no noise or causality inference; identity differences: review |
| c4-16k/requests[2]/max_inter_event_gap_s | 3.97894 [3.97894–3.97894]; 1 | 3.68111 [3.68111–3.68111]; 1 | -0.297832 | -7.4852 | n≤2; no noise or causality inference; identity differences: review |
| c4-16k/requests[2]/ttft_s | 9.81237 [9.81237–9.81237]; 1 | 8.92023 [8.92023–8.92023]; 1 | -0.892135 | -9.09194 | n≤2; no noise or causality inference; identity differences: review |
| c4-16k/requests[3]/decode_tok_s | 48.9024 [48.9024–48.9024]; 1 | 50.2586 [50.2586–50.2586]; 1 | 1.3562 | 2.77329 | n≤2; no noise or causality inference; identity differences: review |
| c4-16k/requests[3]/effective_prefill_tok_s | 1286.61 [1286.61–1286.61]; 1 | 1419.2 [1419.2–1419.2]; 1 | 132.593 | 10.3056 | n≤2; no noise or causality inference; identity differences: review |
| c4-16k/requests[3]/elapsed_s | 20.8934 [20.8934–20.8934]; 1 | 19.4835 [19.4835–19.4835]; 1 | -1.4099 | -6.74809 | n≤2; no noise or causality inference; identity differences: review |
| c4-16k/requests[3]/inter_event_gap_p95_s | 0.0772462 [0.0772462–0.0772462]; 1 | 0.0774879 [0.0774879–0.0774879]; 1 | 0.000241662 | 0.312846 | slower: review; n≤2; no noise or causality inference; identity differences: review |
| c4-16k/requests[3]/max_inter_event_gap_s | 0.0898157 [0.0898157–0.0898157]; 1 | 0.105281 [0.105281–0.105281]; 1 | 0.0154655 | 17.2192 | slower: review; n≤2; no noise or causality inference; identity differences: review |
| c4-16k/requests[3]/ttft_s | 12.7343 [12.7343–12.7343]; 1 | 11.5445 [11.5445–11.5445]; 1 | -1.18973 | -9.34277 | n≤2; no noise or causality inference; identity differences: review |
| c4-16k/summary/aggregate_decode_tok_s | 78.0804 [78.0804–78.0804]; 1 | 82.9711 [82.9711–82.9711]; 1 | 4.89073 | 6.2637 | harness summary; n counts summaries, not requests; identity differences: review |
| c4-16k/summary/aggregate_effective_prefill_tok_s | 4165.26 [4165.26–4165.26]; 1 | 4505.98 [4505.98–4505.98]; 1 | 340.712 | 8.17983 | harness summary; n counts summaries, not requests; identity differences: review |
| c4-16k/summary/decode_tok_s_p50 | 29.2891 [29.2891–29.2891]; 1 | 30.1702 [30.1702–30.1702]; 1 | 0.881142 | 3.00843 | harness summary; n counts summaries, not requests; identity differences: review |
| c4-16k/summary/decode_tok_s_sum | 127.865 [127.865–127.865]; 1 | 131.943 [131.943–131.943]; 1 | 4.07724 | 3.1887 | harness summary; n counts summaries, not requests; identity differences: review |
| c4-16k/summary/effective_prefill_tok_s_p50 | 2024.21 [2024.21–2024.21]; 1 | 2219.62 [2219.62–2219.62]; 1 | 195.402 | 9.65321 | harness summary; n counts summaries, not requests; identity differences: review |
| c4-16k/summary/ttft_p50_s | 8.35008 [8.35008–8.35008]; 1 | 7.60785 [7.60785–7.60785]; 1 | -0.742235 | -8.88895 | harness summary; n counts summaries, not requests; identity differences: review |
| c4-16k/summary/ttft_p95_s | 12.7343 [12.7343–12.7343]; 1 | 11.5445 [11.5445–11.5445]; 1 | -1.18973 | -9.34277 | harness summary; n counts summaries, not requests; identity differences: review |
| c4-16k/summary/wall_s | 24.371 [24.371–24.371]; 1 | 22.8735 [22.8735–22.8735]; 1 | -1.4975 | -6.14462 | harness summary; n counts summaries, not requests; identity differences: review |

