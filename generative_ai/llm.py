"""
Proveedores de modelo de lenguaje (opcionales). Solo usan la libreria estandar.
LLM_PROVIDER = none | ollama | openai | anthropic   (en .env)
- ollama   : local, gratis; los datos NO salen de tu computadora.
- openai / anthropic : servicio externo; solo reciben la pregunta y cifras AGREGADAS
                       (nunca nombres de clientes ni filas individuales).
"""
import json
import os
import urllib.error
import urllib.request


class LLMError(Exception):
    pass


def _post(url: str, payload: dict, headers: dict, timeout: int) -> dict:
    req = urllib.request.Request(url, data=json.dumps(payload).encode("utf-8"),
                                 headers={"Content-Type": "application/json", **headers}, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        raise LLMError(f"El servicio de IA respondio {exc.code}") from None      # sin exponer llaves
    except Exception as exc:  # noqa: BLE001
        raise LLMError(f"No se pudo contactar al servicio de IA ({type(exc).__name__})") from None


class Provider:
    name = "none"
    external = False

    def chat(self, system: str, user: str, json_mode: bool = False, max_tokens: int = 400) -> str:
        raise NotImplementedError


class OllamaProvider(Provider):
    external = False

    def __init__(self):
        self.url = os.getenv("OLLAMA_URL", "http://localhost:11434").rstrip("/")
        self.model = os.getenv("OLLAMA_MODEL", "llama3.2:3b")
        self.name = f"ollama:{self.model}"

    def chat(self, system, user, json_mode=False, max_tokens=400):
        payload = {"model": self.model, "stream": False, "options": {"temperature": 0, "num_predict": max_tokens},
                   "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}]}
        if json_mode:
            payload["format"] = "json"
        return _post(self.url + "/api/chat", payload, {}, 180)["message"]["content"]


class OpenAIProvider(Provider):
    external = True

    def __init__(self):
        self.key = os.environ["OPENAI_API_KEY"]
        self.model = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
        self.name = f"openai:{self.model}"

    def chat(self, system, user, json_mode=False, max_tokens=400):
        payload = {"model": self.model, "temperature": 0, "max_tokens": max_tokens,
                   "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}]}
        if json_mode:
            payload["response_format"] = {"type": "json_object"}
        data = _post("https://api.openai.com/v1/chat/completions", payload,
                     {"Authorization": "Bearer " + self.key}, 60)
        return data["choices"][0]["message"]["content"]


class AnthropicProvider(Provider):
    external = True

    def __init__(self):
        self.key = os.environ["ANTHROPIC_API_KEY"]
        self.model = os.getenv("ANTHROPIC_MODEL", "claude-haiku-5-5")
        self.name = f"anthropic:{self.model}"

    def chat(self, system, user, json_mode=False, max_tokens=400):
        payload = {"model": self.model, "max_tokens": max_tokens, "temperature": 0, "system": system,
                   "messages": [{"role": "user", "content": user}]}
        data = _post("https://api.anthropic.com/v1/messages", payload,
                     {"x-api-key": self.key, "anthropic-version": "2023-06-01"}, 60)
        return "".join(b.get("text", "") for b in data.get("content", []))


def get_provider() -> Provider | None:
    """None = sin modelo de lenguaje (el asistente responde solo con reglas y datos)."""
    name = os.getenv("LLM_PROVIDER", "none").strip().lower()
    if name in ("", "none"):
        return None
    table = {"ollama": OllamaProvider, "openai": OpenAIProvider, "anthropic": AnthropicProvider}
    if name not in table:
        raise ValueError(f"LLM_PROVIDER desconocido: {name}")
    return table[name]()
