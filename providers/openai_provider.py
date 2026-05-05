from __future__ import annotations

import base64
import io
import json
import re
from dataclasses import dataclass
from typing import Any, Dict, Iterable, List, Optional

try:
    from PIL import Image
except Exception:  # pragma: no cover - optional runtime dependency is already in requirements
    Image = None  # type: ignore

try:
    from tools.friday_settings_store import (
        get_friday_response_language_instruction,
        get_openai_api_key,
        get_openai_text_model,
        get_openai_vision_model,
    )
except Exception:  # Safe import fallback for direct module tests
    def get_friday_response_language_instruction() -> str:
        return "Her zaman Türkçe cevap ver."

    def get_openai_api_key() -> str:
        import os
        return os.getenv("OPENAI_API_KEY", "")

    def get_openai_text_model() -> str:
        return "gpt-4.1-mini"

    def get_openai_vision_model() -> str:
        return "gpt-4.1-mini"


@dataclass
class OpenAIToolCall:
    id: str
    name: str
    args: Dict[str, Any]


@dataclass
class OpenAICommandResult:
    text: str = ""
    tool_calls: List[OpenAIToolCall] | None = None
    error: str = ""


def _client():
    key = (get_openai_api_key() or "").strip()
    if not key:
        raise RuntimeError("OpenAI API key is empty. Add it from FRIDAY Settings > OpenAI.")
    try:
        from openai import OpenAI  # type: ignore
    except Exception as exc:
        raise RuntimeError("OpenAI Python package is missing. Run: pip install openai") from exc
    return OpenAI(api_key=key)


def _output_text_from_response(response: Any) -> str:
    text = getattr(response, "output_text", None)
    if text:
        return str(text).strip()
    chunks: List[str] = []
    for item in getattr(response, "output", []) or []:
        for content in getattr(item, "content", []) or []:
            value = getattr(content, "text", None)
            if value:
                chunks.append(str(value))
    return re.sub(r"\s+", " ", " ".join(chunks)).strip()


def _data_url(image_bytes: bytes, mime_type: str) -> str:
    mt = str(mime_type or "image/jpeg").strip() or "image/jpeg"
    return f"data:{mt};base64," + base64.b64encode(image_bytes).decode("ascii")


def analyze_image_bytes(image_bytes: bytes, mime_type: str, prompt: str, *, model: Optional[str] = None) -> str:
    """Analyze one image using OpenAI vision.

    Uses Responses API first and falls back to Chat Completions for older SDKs.
    """
    client = _client()
    model = (model or get_openai_vision_model() or "gpt-4.1-mini").strip()
    instructions = (
        "You are F.R.I.D.A.Y, MEDPOV's private desktop AI assistant. "
        "Analyze the image precisely. Answer in one short sentence unless the user explicitly asks for details. "
        "Do not repeat prior assistant wording. "
        + get_friday_response_language_instruction()
    )
    data_url = _data_url(image_bytes, mime_type)

    try:
        response = client.responses.create(
            model=model,
            instructions=instructions,
            input=[
                {
                    "role": "user",
                    "content": [
                        {"type": "input_text", "text": prompt},
                        {"type": "input_image", "image_url": data_url},
                    ],
                }
            ],
        )
        text = _output_text_from_response(response)
        if text:
            return text
    except Exception as first_exc:
        # Keep a compact diagnostic and then try the legacy-compatible path.
        print(f"[OpenAI Vision] Responses API fallback: {first_exc}")

    completion = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": instructions},
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": prompt},
                    {"type": "image_url", "image_url": {"url": data_url}},
                ],
            },
        ],
        max_tokens=160,
    )
    return str(completion.choices[0].message.content or "").strip()


def generate_text(prompt: str, *, system: Optional[str] = None, model: Optional[str] = None) -> str:
    client = _client()
    model = (model or get_openai_text_model() or "gpt-4.1-mini").strip()
    system = system or ("You are F.R.I.D.A.Y, MEDPOV's private desktop AI assistant. " + get_friday_response_language_instruction())
    try:
        response = client.responses.create(
            model=model,
            instructions=system,
            input=prompt,
        )
        text = _output_text_from_response(response)
        if text:
            return text
    except Exception as first_exc:
        print(f"[OpenAI Text] Responses API fallback: {first_exc}")
    completion = client.chat.completions.create(
        model=model,
        messages=[{"role": "system", "content": system}, {"role": "user", "content": prompt}],
        max_tokens=500,
    )
    return str(completion.choices[0].message.content or "").strip()


def generate_from_mixed_content(contents: Any, *, model: Optional[str] = None) -> str:
    """Compatibility adapter for file_processor style contents.

    Accepts plain text or [prompt, PIL.Image] and routes to OpenAI text/vision.
    """
    if isinstance(contents, str):
        return generate_text(contents, model=model)
    if isinstance(contents, (list, tuple)) and contents:
        prompt = str(contents[0] or "Analyze this file.")
        maybe_image = contents[1] if len(contents) > 1 else None
        if Image is not None and hasattr(maybe_image, "save"):
            buf = io.BytesIO()
            maybe_image.convert("RGB").save(buf, format="JPEG", quality=70)
            return analyze_image_bytes(buf.getvalue(), "image/jpeg", prompt, model=model or get_openai_vision_model())
        return generate_text("\n\n".join(str(x) for x in contents if x is not None), model=model)
    return generate_text(str(contents or ""), model=model)


def _lower_schema(value: Any) -> Any:
    if isinstance(value, dict):
        out: Dict[str, Any] = {}
        for k, v in value.items():
            if k == "type" and isinstance(v, str):
                out[k] = v.lower()
            elif k == "properties" and isinstance(v, dict):
                out[k] = {name: _lower_schema(schema) for name, schema in v.items()}
            elif k == "items":
                out[k] = _lower_schema(v)
            else:
                out[k] = _lower_schema(v)
        return out
    if isinstance(value, list):
        return [_lower_schema(x) for x in value]
    return value


def _to_openai_tools(tool_declarations: Iterable[Dict[str, Any]]) -> List[Dict[str, Any]]:
    tools: List[Dict[str, Any]] = []
    for decl in tool_declarations:
        name = str(decl.get("name") or "").strip()
        if not name:
            continue
        params = _lower_schema(decl.get("parameters") or {"type": "object", "properties": {}})
        params.setdefault("type", "object")
        tools.append(
            {
                "type": "function",
                "function": {
                    "name": name,
                    "description": str(decl.get("description") or ""),
                    "parameters": params,
                },
            }
        )
    return tools


def route_command(user_text: str, tool_declarations: Iterable[Dict[str, Any]], *, system_prompt: Optional[str] = None) -> OpenAICommandResult:
    """Route a FRIDAY text/voice command through OpenAI with local tools.

    The function returns either natural text or tool calls. The caller executes the
    tools locally, so OpenAI never receives local files, secrets, or desktop state
    unless a specific tool result is later summarized by the app.
    """
    try:
        client = _client()
        tools = _to_openai_tools(tool_declarations)
        system = system_prompt or (
            "You are F.R.I.D.A.Y, MEDPOV's private desktop AI command center. "
            "Use tools whenever the user asks you to operate the computer, camera, files, browser, reminders, or Security Center. "
            "Do not pretend to have completed an action without selecting a tool. "
            "If the text looks like a fragment of your own previous answer or an unclear speech-to-text echo, ask for clarification without using tools. "
            + get_friday_response_language_instruction()
        )
        completion = client.chat.completions.create(
            model=(get_openai_text_model() or "gpt-4.1-mini"),
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user_text},
            ],
            tools=tools,
            tool_choice="auto",
            temperature=0.2,
            max_tokens=360,
        )
        msg = completion.choices[0].message
        tool_calls: List[OpenAIToolCall] = []
        for call in getattr(msg, "tool_calls", []) or []:
            fn = getattr(call, "function", None)
            if not fn:
                continue
            args_raw = getattr(fn, "arguments", "{}") or "{}"
            try:
                args = json.loads(args_raw) if isinstance(args_raw, str) else dict(args_raw)
            except Exception:
                args = {}
            tool_calls.append(OpenAIToolCall(id=str(getattr(call, "id", "openai_tool_call")), name=str(getattr(fn, "name", "")), args=args))
        return OpenAICommandResult(text=str(getattr(msg, "content", "") or "").strip(), tool_calls=tool_calls)
    except Exception as exc:
        return OpenAICommandResult(error=str(exc))
