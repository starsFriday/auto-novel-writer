from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Any


class LLMError(RuntimeError):
    pass


@dataclass
class LLMClient:
    model: str
    base_url: str = "https://api.openai.com/v1"
    api_key_env: str = "OPENAI_API_KEY"
    temperature: float = 0.7
    max_tokens: int = 4096
    request_timeout: int = 120
    retries: int = 3
    retry_sleep_seconds: int = 2

    @property
    def api_key(self) -> str:
        value = os.environ.get(self.api_key_env, "")
        if not value:
            raise LLMError(f"Missing API key env var: {self.api_key_env}")
        return value

    def complete(self, messages: list[dict[str, str]], temperature: float | None = None) -> str:
        last_error: Exception | None = None
        for attempt in range(1, self.retries + 1):
            try:
                return self._complete_with_sdk(messages, temperature)
            except ImportError:
                return self._complete_with_urllib(messages, temperature)
            except Exception as exc:
                last_error = exc
                if attempt >= self.retries:
                    break
                time.sleep(self.retry_sleep_seconds * attempt)
        raise LLMError(str(last_error))

    def complete_json(self, messages: list[dict[str, str]], temperature: float | None = None) -> Any:
        last_error: Exception | None = None
        for attempt in range(1, self.retries + 1):
            text = self.complete(messages, temperature=temperature)
            try:
                return extract_json(text)
            except Exception as exc:
                last_error = exc
                if attempt >= self.retries:
                    break
                time.sleep(self.retry_sleep_seconds * attempt)
        raise LLMError(str(last_error))

    def _supports_custom_temperature(self) -> bool:
        normalized = self.model.strip().lower()
        # Current reasoning/frontier models often only accept the default
        # sampling temperature. Omitting the field lets the API use that default.
        return not (
            normalized.startswith("gpt-5")
            or normalized.startswith("o1")
            or normalized.startswith("o3")
            or normalized.startswith("o4")
        )

    def _build_payload(self, messages: list[dict[str, str]], temperature: float | None) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "model": self.model,
            "messages": messages,
            "max_tokens": self.max_tokens,
        }
        if self._supports_custom_temperature():
            payload["temperature"] = self.temperature if temperature is None else temperature
        return payload

    def _complete_with_sdk(self, messages: list[dict[str, str]], temperature: float | None) -> str:
        from openai import OpenAI

        client = OpenAI(
            api_key=self.api_key,
            base_url=self.base_url,
            timeout=self.request_timeout,
        )
        kwargs = self._build_payload(messages, temperature)
        try:
            response = client.chat.completions.create(**kwargs)
        except Exception as exc:
            message = str(exc)
            if "temperature" in message:
                kwargs.pop("temperature", None)
                response = client.chat.completions.create(**kwargs)
            elif "max_tokens" in message:
                kwargs.pop("max_tokens", None)
                kwargs["max_completion_tokens"] = self.max_tokens
                response = client.chat.completions.create(**kwargs)
            else:
                raise
        content = response.choices[0].message.content
        if not content:
            raise LLMError("Empty response from LLM")
        return content

    def _complete_with_urllib(self, messages: list[dict[str, str]], temperature: float | None) -> str:
        url = self.base_url.rstrip("/") + "/chat/completions"
        payload = self._build_payload(messages, temperature)
        request = urllib.request.Request(
            url,
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=self.request_timeout) as response:
                body = json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            raise LLMError(f"HTTP {exc.code}: {detail}") from exc
        return body["choices"][0]["message"]["content"]


def extract_json(text: str) -> Any:
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.strip("`")
        cleaned = cleaned.removeprefix("json").strip()
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        pass

    start = None
    stack: list[str] = []
    in_string = False
    escape = False
    for index, char in enumerate(text):
        if start is None:
            if char in "{[":
                start = index
                stack.append("}" if char == "{" else "]")
            continue
        if in_string:
            if escape:
                escape = False
            elif char == "\\":
                escape = True
            elif char == '"':
                in_string = False
            continue
        if char == '"':
            in_string = True
        elif char in "{[":
            stack.append("}" if char == "{" else "]")
        elif char in "}]":
            if not stack or char != stack[-1]:
                continue
            stack.pop()
            if not stack:
                candidate = text[start : index + 1]
                return json.loads(candidate)
    raise ValueError("No valid JSON object found in LLM output")


def resolve_llm_config(config: dict[str, Any]) -> dict[str, Any]:
    llm_cfg = dict(config["llm"])
    profile = os.environ.get("LLM_PROFILE", "").strip().lower() or str(llm_cfg.get("provider", "")).strip().lower()

    if profile in {"openai", "official"}:
        llm_cfg["provider"] = "openai"
        llm_cfg["base_url"] = os.environ.get("OPENAI_BASE_URL", "https://api.openai.com/v1")
        llm_cfg["api_key_env"] = "OPENAI_API_KEY"
        llm_cfg["model"] = os.environ.get("OPENAI_MODEL", llm_cfg.get("model", "gpt-5.5"))
        llm_cfg["judge_model"] = os.environ.get("OPENAI_JUDGE_MODEL", llm_cfg.get("judge_model", llm_cfg["model"]))
        return llm_cfg

    if profile in {"codex-lb", "codex_lb", "vvicat"}:
        llm_cfg["provider"] = "codex-lb"
        llm_cfg["base_url"] = os.environ.get("CODEX_LB_BASE_URL", "https://codex-lb.vvicat.dev/v1")
        llm_cfg["api_key_env"] = "CODEX_LB_API_KEY" if os.environ.get("CODEX_LB_API_KEY") else "OPENAI_API_KEY"
        llm_cfg["model"] = os.environ.get("CODEX_LB_MODEL", llm_cfg.get("model", "gpt-5.5"))
        llm_cfg["judge_model"] = os.environ.get("CODEX_LB_JUDGE_MODEL", llm_cfg.get("judge_model", llm_cfg["model"]))
        return llm_cfg

    return llm_cfg


def make_llm_client(config: dict[str, Any], judge: bool = False) -> LLMClient:
    from .config import PROJECT_ROOT
    from .io_utils import load_env_file

    load_env_file(PROJECT_ROOT / ".env")
    llm_cfg = resolve_llm_config(config)
    return LLMClient(
        model=llm_cfg["judge_model"] if judge else llm_cfg["model"],
        base_url=llm_cfg["base_url"],
        api_key_env=llm_cfg["api_key_env"],
        temperature=llm_cfg["judge_temperature"] if judge else llm_cfg["temperature"],
        max_tokens=int(llm_cfg["max_tokens"]),
        request_timeout=int(llm_cfg["request_timeout"]),
        retries=int(llm_cfg["retries"]),
        retry_sleep_seconds=int(llm_cfg["retry_sleep_seconds"]),
    )
