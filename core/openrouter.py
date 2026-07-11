import requests
import json
import os
import datetime

USAGE_FILE = os.path.abspath("./temp_backups/openrouter_usage.json")
MAX_DAILY_REQUESTS = 900

def get_openrouter_request_count() -> int:
    if not os.path.exists(USAGE_FILE):
        return 0
    try:
        with open(USAGE_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        today = datetime.date.today().isoformat()
        if data.get("date") == today:
            return data.get("count", 0)
    except Exception:
        pass
    return 0

def increment_openrouter_request_count():
    os.makedirs(os.path.dirname(USAGE_FILE), exist_ok=True)
    today = datetime.date.today().isoformat()
    count = 0
    if os.path.exists(USAGE_FILE):
        try:
            with open(USAGE_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
            if data.get("date") == today:
                count = data.get("count", 0)
        except Exception:
            pass
    count += 1
    try:
        with open(USAGE_FILE, "w", encoding="utf-8") as f:
            json.dump({"date": today, "count": count}, f)
    except Exception:
        pass
    return count

class OpenRouterClient:
    def __init__(self, api_key: str, model_name: str):
        self.api_key = api_key
        self.model_name = model_name
        self.config = FakeConfig()

    def generate_stream(self, messages: list[dict], temp: float = 0.3, max_tokens: int = 1500):
        current_count = get_openrouter_request_count()
        if current_count >= MAX_DAILY_REQUESTS:
            raise RuntimeError(f"오늘의 오픈라우터 일일 API 호출 권장 제한({MAX_DAILY_REQUESTS}회)에 도달했습니다. 무료 제공량 초과 방지를 위해 작동을 일시 정지합니다.")

        # Increment count
        increment_openrouter_request_count()

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            "HTTP-Referer": "https://github.com/Persona-Translator",
            "X-Title": "Persona Translator",
        }
        
        payload = {
            "model": self.model_name,
            "messages": messages,
            "temperature": temp,
            "max_tokens": max_tokens,
            "stream": True
        }
        
        try:
            response = requests.post(
                "https://openrouter.ai/api/v1/chat/completions",
                headers=headers,
                json=payload,
                stream=True,
                timeout=30
            )
        except Exception as e:
            raise RuntimeError(f"네트워크 오류: {e}")
            
        if response.status_code != 200:
            err_data = response.text
            try:
                err_json = response.json()
                if "error" in err_json:
                    err_data = err_json["error"].get("message", err_data)
            except Exception:
                pass
            raise RuntimeError(f"오픈라우터 API 오류 ({response.status_code}): {err_data}")
            
        for line in response.iter_lines():
            if line:
                line_str = line.decode("utf-8").strip()
                if line_str.startswith("data: "):
                    data_content = line_str[6:]
                    if data_content == "[DONE]":
                        break
                    try:
                        chunk_json = json.loads(data_content)
                        choice = chunk_json["choices"][0]
                        delta = choice.get("delta", {})
                        text = delta.get("content", "")
                        if text:
                            yield OpenRouterResponseChunk(text)
                    except Exception:
                        pass

    def generate(self, messages: list[dict], temp: float = 0.3, max_tokens: int = 1500):
        current_count = get_openrouter_request_count()
        if current_count >= MAX_DAILY_REQUESTS:
            raise RuntimeError(f"오늘의 오픈라우터 일일 API 호출 권장 제한({MAX_DAILY_REQUESTS}회)에 도달했습니다. 무료 제공량 초과 방지를 위해 작동을 일시 정지합니다.")

        # Increment count
        increment_openrouter_request_count()

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            "HTTP-Referer": "https://github.com/Persona-Translator",
            "X-Title": "Persona Translator",
        }
        
        payload = {
            "model": self.model_name,
            "messages": messages,
            "temperature": temp,
            "max_tokens": max_tokens,
            "stream": False
        }
        
        try:
            response = requests.post(
                "https://openrouter.ai/api/v1/chat/completions",
                headers=headers,
                json=payload,
                stream=False,
                timeout=30
            )
        except Exception as e:
            raise RuntimeError(f"네트워크 오류: {e}")
            
        if response.status_code != 200:
            err_data = response.text
            try:
                err_json = response.json()
                if "error" in err_json:
                    err_data = err_json["error"].get("message", err_data)
            except Exception:
                pass
            raise RuntimeError(f"오픈라우터 API 오류 ({response.status_code}): {err_data}")
            
        try:
            res_json = response.json()
            text = res_json["choices"][0]["message"]["content"]
            return OpenRouterResponseChunk(text)
        except Exception as e:
            raise RuntimeError(f"오픈라우터 응답 파싱 실패: {e}")

class OpenRouterResponseChunk:
    def __init__(self, text):
        self.text = text

class FakeConfig:
    def __init__(self):
        self.model_type = "openrouter"
        self.architectures = ["OpenRouterModel"]
