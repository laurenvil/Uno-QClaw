# QClaw Cloud API User Guide

This guide covers connecting QClaw to cloud-based LLM providers: Anthropic (direct),
OpenRouter, OpenAI, and any OpenAI-compatible endpoint. No code changes required —
everything is config-only.

---

## How Providers Work in QClaw

QClaw selects a provider from `model_list` in `~/.qclaw/config.json`. The `model` field
carries a protocol prefix that determines which provider implementation is used:

```
"model": "<protocol>/<model-id>"
```

The active model is set in `agents.defaults.model_name`. Switching providers is a config
change only — no rebuild needed.

---

## Supported Cloud Protocols

| Protocol prefix | Provider | Auth |
|---|---|---|
| `anthropic-messages` | Anthropic API (native format) | `api_key` |
| `openrouter` | OpenRouter | `api_key` |
| `openai` | OpenAI | `api_key` |
| `anthropic` | Anthropic via proxy / LiteLLM | `api_key` + `api_base` |
| `litellm` | LiteLLM proxy | `api_key` + `api_base` |
| `azure` | Azure OpenAI | `api_key` + `api_base` |

---

## Quick Start: Anthropic Direct (Recommended for Claude)

The `anthropic-messages` protocol speaks the native Anthropic Messages API. It supports
tool use, streaming, and all Claude models without a proxy.

**1. Get an API key**  
→ [console.anthropic.com](https://console.anthropic.com) → API Keys → Create Key

**2. Add the model entry to `~/.qclaw/config.json`**

```jsonc
{
  "model_list": [
    {
      "model_name": "claude-sonnet",
      "model": "anthropic-messages/claude-sonnet-4-6",
      "api_key": "sk-ant-YOUR_KEY_HERE",
      "request_timeout": 120,
      "max_tokens": 4096
    }
  ],
  "agents": {
    "defaults": {
      "model_name": "claude-sonnet",
      "model": "claude-sonnet",
      "temperature": 0.3,
      "max_tokens": 4096,
      "max_tool_iterations": 8
    }
  }
}
```

**3. Test it**

```bash
qclaw direct -m "Which pins on the Uno Q support PWM?"
```

**Available Claude models (as of 2026-05)**

| Model ID | Context | Notes |
|---|---|---|
| `claude-sonnet-4-6` | 200K | Best balance of speed + quality |
| `claude-opus-4-7` | 200K | Highest capability, slower |
| `claude-haiku-4-5-20251001` | 200K | Fastest, lowest cost |

---

## OpenRouter

OpenRouter proxies dozens of providers (Anthropic, OpenAI, Google, Meta) behind a single
OpenAI-compatible API. Useful if you want one key for multiple models or don't have a
direct Anthropic account.

**1. Get an API key**  
→ [openrouter.ai/keys](https://openrouter.ai/keys)

**2. Config entry**

```jsonc
{
  "model_name": "claude-openrouter",
  "model": "openrouter/anthropic/claude-sonnet-4-5",
  "api_key": "sk-or-YOUR_KEY_HERE",
  "request_timeout": 120,
  "max_tokens": 4096
}
```

**Useful OpenRouter model IDs for QClaw**

| Model string | Provider |
|---|---|
| `anthropic/claude-sonnet-4-5` | Anthropic Claude |
| `anthropic/claude-opus-4` | Anthropic Claude Opus |
| `openai/gpt-4o` | OpenAI |
| `google/gemini-2.0-flash-001` | Google |
| `meta-llama/llama-3.3-70b-instruct` | Meta (free tier available) |

---

## OpenAI

```jsonc
{
  "model_name": "gpt4o",
  "model": "openai/gpt-4o",
  "api_key": "sk-YOUR_OPENAI_KEY",
  "request_timeout": 120,
  "max_tokens": 4096
}
```

No `api_base` needed — defaults to `https://api.openai.com/v1`.

---

## Azure OpenAI

Azure requires a deployment-specific URL and uses `api-key` header auth (not Bearer).

```jsonc
{
  "model_name": "azure-gpt4o",
  "model": "azure/gpt-4o",
  "api_key": "YOUR_AZURE_API_KEY",
  "api_base": "https://YOUR-RESOURCE.openai.azure.com",
  "request_timeout": 120,
  "max_tokens": 4096
}
```

The deployment name is taken from the model ID after the `/` prefix.

---

## LiteLLM Proxy (Self-Hosted)

LiteLLM lets you run a local proxy that routes to any provider with a unified API.
Useful for teams sharing a single gateway.

```jsonc
{
  "model_name": "litellm-claude",
  "model": "litellm/claude-sonnet-4-6",
  "api_key": "YOUR_LITELLM_KEY",
  "api_base": "http://localhost:4000/v1",
  "request_timeout": 120
}
```

---

## Switching Between Local and Cloud

You can keep both local (yzma) and cloud entries in `model_list` and switch by changing
`agents.defaults.model_name`:

```jsonc
"agents": {
  "defaults": {
    "model_name": "yzma",      // ← change to "claude-sonnet" for cloud
    "temperature": 0.3,
    "max_tokens": 2048
  }
}
```

Or pass `--model` on the command line for one-off use (direct mode only):

```bash
qclaw direct --model yzma -m "Blink the LED"
```

---

## Tool Use with Cloud Models

All 8 QClaw tools (`arduino`, `write_file`, `read_file`, `camera`, `sysfs_led`,
`network`, `i2cdetect`, `filesystem`) work with any cloud provider that supports tool
use. No config changes needed — the agentic loop handles tool schema translation
automatically per provider.

Providers confirmed to support QClaw tool calls:

| Provider | Tool use |
|---|---|
| `anthropic-messages` | ✅ Native Anthropic tools format |
| `openrouter` | ✅ OpenAI tools format, translated server-side |
| `openai` | ✅ Native OpenAI tools format |
| `azure` | ✅ Same as OpenAI |
| `litellm` | ✅ Proxy handles translation |

---

## Recommended `request_timeout` by Provider

Local inference can take 20+ minutes per prompt. Cloud models are much faster:

| Provider | Recommended timeout |
|---|---|
| Anthropic / OpenAI / OpenRouter | `120` s |
| Azure | `120` s |
| LiteLLM (self-hosted, slow backend) | `300` s |
| Local yzma (Q4_0) | `1200` s |
| Local yzma-q8 (Q8_0) | `2400` s |

---

## Security Notes

- **Never commit `api_key` values.** `~/.qclaw/config.json` is the runtime config and
  is not tracked by git. `config/qclaw.config.json` (the repo template) uses placeholder
  values — keep it that way.
- API keys in `model_list` entries are read at startup. Rotate keys by editing
  `~/.qclaw/config.json` and restarting QClaw — no rebuild required.
- All cloud requests go over HTTPS. No data transits through the Uno Q's MCU side.

---

## Full Example: `~/.qclaw/config.json` with Multiple Providers

```jsonc
{
  "agents": {
    "defaults": {
      "model_name": "yzma",
      "model": "yzma",
      "temperature": 0.3,
      "max_tokens": 2048,
      "max_tool_iterations": 8
    }
  },
  "model_list": [
    {
      "model_name": "yzma",
      "model": "llama-server/Qwen_Qwen3.5-0.8B-Q4_0.gguf",
      "api_base": "engines/yzma/lib/llama-server",
      "api_key": "local",
      "request_timeout": 1200,
      "extra_body": {
        "ctx_size": 16384,
        "threads": 4,
        "parallel": 1,
        "port": 8083,
        "lib_path": "engines/yzma/lib",
        "models_dir": "~/models",
        "extra_args": [
          "--flash-attn", "on", "--mlock",
          "--cache-type-k", "q8_0", "--cache-type-v", "q8_0",
          "--reasoning-budget", "800"
        ]
      }
    },
    {
      "model_name": "claude-sonnet",
      "model": "anthropic-messages/claude-sonnet-4-6",
      "api_key": "sk-ant-YOUR_KEY",
      "request_timeout": 120,
      "max_tokens": 4096
    },
    {
      "model_name": "claude-openrouter",
      "model": "openrouter/anthropic/claude-sonnet-4-5",
      "api_key": "sk-or-YOUR_KEY",
      "request_timeout": 120,
      "max_tokens": 4096
    }
  ]
}
```
