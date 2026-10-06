// SPDX-License-Identifier: AGPL-3.0-only
// sd_bench.mjs TAG [types] [concurrencies]  -- the sparkDash decode-bench protocol, headless.
// Protocol and prompts are MiaAI-Lab/sparkDash (MIT, server/collectors/DecodeBench.js and
// src/shared/llmPrompts.js, imported from a local checkout, not copied): temperature 0, top_p 1,
// thinking off, 400 forced tokens (min_tokens + ignore_eos), a 32-token warmup per type,
// per-stream decode tok/s = (completion_tokens - 1) / (last - first token), aggregate =
// sum(decode tokens) / (max last - min first). Writes ~/sparkqwen-dev/sd-TAG.json.
import { pickDecodeBenchPrompts, DECODE_CODE_WARMUP_PROMPT, decodeBenchPromptForType } from
  "<home>/sparkDash/src/shared/llmPrompts.js";
import { writeFileSync } from "node:fs";

const URL = process.env.SQ_URL || "http://127.0.0.1:8893";
const MODEL = process.env.SQ_MODEL || "qwen3.8-flash-next-atlas";
const MAX = Number(process.env.SD_MAX || 400);
const [tag, typesArg = "structured,prose,code,json", concArg = "1,2,4,8"] = process.argv.slice(2);
const think = { enable_thinking: false, thinking: false, thinking_mode: "disabled" };

async function stream(prompt, maxTokens, force) {
  const body = { model: MODEL, messages: [{ role: "user", content: prompt }], max_tokens: maxTokens,
    temperature: 0, top_p: 1, stream: true, stream_options: { include_usage: true }, chat_template_kwargs: think };
  if (force) { body.min_tokens = maxTokens; body.ignore_eos = true; }
  const t0 = performance.now(); let tFirst = null, tLast = null, usage = null, buf = "";
  const r = await fetch(`${URL}/v1/chat/completions`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
  if (!r.ok) throw new Error(`HTTP ${r.status}: ${await r.text()}`);
  for await (const chunk of r.body) {
    buf += Buffer.from(chunk).toString();
    let i;
    while ((i = buf.indexOf("\n")) >= 0) {
      const line = buf.slice(0, i).trim(); buf = buf.slice(i + 1);
      if (!line.startsWith("data:") || line === "data: [DONE]") continue;
      const d = JSON.parse(line.slice(5));
      if (d.usage) usage = d.usage;
      for (const c of d.choices || []) {
        const p = (c.delta?.content || "") + (c.delta?.reasoning_content || c.delta?.reasoning || "");
        if (p) { const now = performance.now(); if (tFirst === null) tFirst = now; tLast = now; }
      }
    }
  }
  const n = usage?.completion_tokens ?? 0;
  return { t0, tFirst, tLast, n, prompt: usage?.prompt_tokens, ttftMs: tFirst - t0,
    tps: n > 1 && tLast > tFirst ? (n - 1) / ((tLast - tFirst) / 1000) : 0 };
}
const median = (a) => { const s = [...a].sort((x, y) => x - y); const m = s.length >> 1; return s.length % 2 ? s[m] : (s[m - 1] + s[m]) / 2; };
const out = { tag, date: new Date().toISOString(), protocol: "sparkDash decode bench (MiaAI-Lab, MIT)", max: MAX, waves: [] };
for (const type of typesArg.split(",")) {
  await stream(type === "code" ? DECODE_CODE_WARMUP_PROMPT : decodeBenchPromptForType(type), 32, true);
  for (const c of concArg.split(",").map(Number)) {
    const prompts = pickDecodeBenchPrompts(c, type);
    const rs = await Promise.all(prompts.map((p) => stream(p, MAX, true)));
    const tokens = rs.reduce((s, r) => s + Math.max(0, r.n - 1), 0);
    const win = Math.max(...rs.map((r) => r.tLast)) - Math.min(...rs.map((r) => r.tFirst));
    const w = { type, c, medianTps: +median(rs.map((r) => r.tps)).toFixed(2), aggregateTps: +(tokens / win * 1000).toFixed(2),
      medianTtftMs: +median(rs.map((r) => r.ttftMs)).toFixed(1), perStream: rs.map((r) => +r.tps.toFixed(2)) };
    out.waves.push(w);
    console.log(`${type} C${c}: median ${w.medianTps} tok/s, aggregate ${w.aggregateTps}, TTFT ${w.medianTtftMs} ms`);
  }
}
writeFileSync(`${process.env.HOME}/sparkqwen-dev/sd-${tag}.json`, JSON.stringify(out, null, 1));
