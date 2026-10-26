<!-- SPDX-License-Identifier: AGPL-3.0-only -->
# Automatic tool-call protection

SparkQwen 0.3.2 and its Atlas engine block suspicious data-exfiltration tool calls
by default, in both Strict and Spark modes. There is no second model or GPU pass.
Normal prose streams as before; each tool call is held until its arguments pass.

The default policy checks literal cloud metadata destinations, specific reported
callback hosts, recognizable credential-file/environment uploads, private-key
transfers, structured credential payloads, custom-header exports and recognizable
credentials in URLs. Standard Authorization, Proxy-Authorization and X-API-Key
headers remain available for normal API authentication. It also rejects malformed,
truncated recognized calls and arguments over the configured limit. It applies
to parsed tool calls, including the existing reasoning-to-tool recovery path.

## Configure

Set these in `.env` before starting the pair:

```sh
TOOL_GUARD=on
TOOL_GUARD_MAX_BYTES=1048576
# Optional comma-separated exact hosts:
#TOOL_GUARD_ALLOW_HOSTS=uploads.example.org
#TOOL_GUARD_DENY_HOSTS=blocked.example.org
```

`start.sh` forwards the settings to both ranks. Direct container operators use
`SPARKQWEN_TOOL_GUARD`, `SPARKQWEN_TOOL_GUARD_MAX_BYTES`,
`SPARKQWEN_TOOL_GUARD_ALLOW_HOSTS`, and `SPARKQWEN_TOOL_GUARD_DENY_HOSTS`.
The launcher maps them to Atlas's `--tool-guard`, `--tool-guard-max-bytes`,
`--tool-guard-allow-host` and `--tool-guard-deny-host` flags. Requests cannot change
this server policy. Performance profiles cannot duplicate or override its flags.

Host exceptions are exact, with no subdomain wildcards. Explicit denials and
metadata protection take priority. An intentional metadata workflow needs
`TOOL_GUARD=off`; isolate that workflow. Limits are 1 to 67108864 bytes.

## What a block looks like

The client receives a fixed refusal, no blocked tool-call header or arguments,
and Chat Completions `finish_reason: "content_filter"` with `guard_stop: "tool_call_guard"`.
Anthropic uses `stop_reason: "refusal"`. Responses currently returns the fixed
notice as `output_text` in a completed response, without a structured refusal part
or guard marker; the blocked call is still withheld.
The server logs a reason code without repeating the arguments. Earlier safe calls
already released in a streamed turn cannot be recalled. Tool arguments become
visible only after the complete call passes; ordinary text is not buffered by
this feature.

## Scope

This is a lightweight output filter, not a guarantee that arbitrary programs are
safe. It does not scan ordinary prose, infer the user's full intent, interpret
arbitrary code or base64, or stop a script executed later outside Atlas. It cannot
resolve DNS, follow redirects, or police the client application's renderer.
Use an executor sandbox and controlled network egress for those boundaries.

An upload to an organization's endpoint can be legitimate. Review the reason and
use a narrow host exception when appropriate. Calls that write code or documents
can also match these conservative argument checks. There is no provider-wide or
country-based blocklist. The [Cohere report](https://cohere.com/blog/concerning-behaviour-popular-open-weight-ai-model)
does not establish a deliberate model backdoor.
