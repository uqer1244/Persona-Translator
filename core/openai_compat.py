import json

import requests


class OpenAICompatClient:
    """OpenAI 호환 /v1/chat/completions 엔드포인트용 클라이언트.

    base_url 예시:
      - https://api.openai.com/v1  (OpenAI API)
      - http://localhost:8080/v1   (llama.cpp llama-server)
    """

    def __init__(self, base_url: str, api_key: str, model_name: str):
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.model_name = model_name
        self.supports_vision = False
        self.config = FakeConfig()

    def _headers(self) -> dict:
        headers = {"Content-Type": "application/json"}
        if self.api_key.strip():
            headers["Authorization"] = f"Bearer {self.api_key}"
        return headers

    def generate_stream(self, messages: list[dict], temp: float = 0.3, max_tokens: int = 1500):
        payload = {
            "model": self.model_name,
            "messages": messages,
            "temperature": temp,
            "max_tokens": max_tokens,
            "stream": True,
        }
        response = self._request(payload, stream=True)

        for line in response.iter_lines():
            if not line:
                continue
            line_str = line.decode("utf-8").strip()
            if not line_str.startswith("data: "):
                continue
            data_content = line_str[6:]
            if data_content == "[DONE]":
                break
            try:
                chunk_json = json.loads(data_content)
                delta = chunk_json["choices"][0].get("delta", {})
                text = delta.get("content", "")
                if text:
                    yield ResponseChunk(text)
            except Exception:
                pass

    def generate(self, messages: list[dict], temp: float = 0.3, max_tokens: int = 1500):
        payload = {
            "model": self.model_name,
            "messages": messages,
            "temperature": temp,
            "max_tokens": max_tokens,
            "stream": False,
        }
        response = self._request(payload, stream=False)
        try:
            try:
                payload = response.json()
            except ValueError:
                from core.json_repair import parse_json_response
                payload = parse_json_response(response.text)
            text = payload["choices"][0]["message"]["content"]
            return ResponseChunk(text)
        except Exception as e:
            raise RuntimeError(f"OpenAI 호환 API 응답 파싱 실패: {e}")

    def _request(self, payload: dict, stream: bool):
        try:
            response = requests.post(
                f"{self.base_url}/chat/completions",
                headers=self._headers(),
                json=payload,
                stream=stream,
                timeout=120,
            )
        except Exception as e:
            raise RuntimeError(f"네트워크 오류: {e}")

        if response.status_code != 200:
            err_data = response.text
            try:
                err_json = response.json()
                if "error" in err_json:
                    message = err_json["error"]
                    message = message.get("message", err_data) if isinstance(message, dict) else str(message)
                    err_data = message
            except Exception:
                pass
            raise RuntimeError(f"OpenAI 호환 API 오류 ({response.status_code}): {err_data}")
        return response


class ResponseChunk:
    def __init__(self, text):
        self.text = text


class FakeConfig:
    def __init__(self):
        self.model_type = "openai_compat"
        self.architectures = ["OpenAICompatModel"]
