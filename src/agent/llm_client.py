"""Azure AI Foundry chat client (Azure OpenAI-compatible deployments) with JSON output, usage capture and param fallbacks."""
from __future__ import annotations
import json, re, time
from dataclasses import dataclass
from typing import Optional, Protocol
from src.common.config import Settings
from src.common.exceptions import ConfigError, LLMError

@dataclass
class LLMResult:
    data: dict
    prompt_tokens: Optional[int]       # None == usage not reported (never fabricated)
    completion_tokens: Optional[int]
    total_tokens: Optional[int]
    seconds: float
    deployment: str

class LLMClient(Protocol):
    def chat_json(self, deployment: str, system: str, user: str, temperature: float = 0.1, max_tokens: int = 1800) -> LLMResult: ...

def parse_json(text: str) -> dict:
    t = re.sub(r"^```(?:json)?|```$", "", (text or "").strip(), flags=re.M).strip()
    try: return json.loads(t)
    except json.JSONDecodeError:
        m = re.search(r"\{.*\}", t, re.S)
        if m: return json.loads(m.group(0))
        raise

class FoundryLLM:
    def __init__(self, s: Settings):
        if not s.azure_configured: raise ConfigError("AZURE_AI_FOUNDRY_ENDPOINT / AZURE_AI_FOUNDRY_API_KEY are not set (see .env.example)")
        from openai import AzureOpenAI
        self.timeout = s.routing.get("llm", {}).get("timeout_seconds", 60)
        mk = lambda ep, key: AzureOpenAI(azure_endpoint=ep, api_key=key, api_version=s.api_version, timeout=self.timeout, max_retries=2)
        self.client = mk(s.endpoint, s.api_key)
        # optional separate endpoint/key for the open model (e.g. a Llama/Phi/Mistral deployment hosted elsewhere in Foundry)
        self.by_deployment = {s.open_deployment: mk(s.open_endpoint or s.endpoint, s.open_api_key or s.api_key)} if s.open_deployment and (s.open_endpoint or s.open_api_key) else {}

    def _create(self, deployment, messages, temperature, max_tokens, json_mode=True):
        kw = {"model": deployment, "messages": messages, "temperature": temperature, "max_completion_tokens": max_tokens}
        if json_mode: kw["response_format"] = {"type": "json_object"}
        for _ in range(4):                       # progressively drop parameters a given deployment rejects
            try: return self.by_deployment.get(deployment, self.client).chat.completions.create(**kw)
            except Exception as e:
                m = str(e).lower()
                if "max_completion_tokens" in m and "max_completion_tokens" in kw: kw["max_tokens"] = kw.pop("max_completion_tokens")
                elif "temperature" in m and "temperature" in kw: kw.pop("temperature")
                elif ("response_format" in m or "json" in m) and "response_format" in kw: kw.pop("response_format")
                elif "max_tokens" in m and "max_tokens" in kw: kw.pop("max_tokens")
                else: raise LLMError(f"Azure AI Foundry call failed for deployment '{deployment}': {e}") from e
        raise LLMError(f"Azure AI Foundry call failed for deployment '{deployment}' after parameter fallbacks")

    def chat_json(self, deployment, system, user, temperature=0.1, max_tokens=1800) -> LLMResult:
        if not deployment: raise ConfigError("model deployment name is empty - set AZURE_OPEN_MODEL_DEPLOYMENT / AZURE_FRONTIER_MODEL_DEPLOYMENT")
        msgs = [{"role": "system", "content": system}, {"role": "user", "content": user}]; t0 = time.time(); pt = ct = tt = None
        for attempt in range(2):
            r = self._create(deployment, msgs, temperature, max_tokens)
            u = getattr(r, "usage", None)
            if u is not None:
                pt = (pt or 0) + (u.prompt_tokens or 0); ct = (ct or 0) + (u.completion_tokens or 0); tt = (tt or 0) + (u.total_tokens or 0)
            text = r.choices[0].message.content if r.choices else ""
            try: return LLMResult(parse_json(text), pt, ct, tt, time.time() - t0, deployment)
            except Exception:
                msgs += [{"role": "assistant", "content": text or ""}, {"role": "user", "content": "Your reply was not valid JSON. Reply with ONLY the JSON object."}]
        raise LLMError(f"deployment '{deployment}' returned invalid JSON twice")
