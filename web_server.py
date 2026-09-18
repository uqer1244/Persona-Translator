from __future__ import annotations

import asyncio
import json
import os
import queue
import uuid
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from typing import Any

import requests
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from core.document import chunk_srt, chunk_text
from core.openai_compat import OpenAICompatClient
from core.json_repair import parse_json_response
from core.translator import (
    build_retranslation_prompt,
    build_translation_prompt,
    clean_markdown,
    extract_final_translation,
    translate_one_chunk,
    translate_script,
)


ROOT = os.path.dirname(os.path.abspath(__file__))
WEB_DIR = os.path.join(ROOT, "web")
EXECUTOR = ThreadPoolExecutor(max_workers=4, thread_name_prefix="translation")


class ProjectRequest(BaseModel):
    script: str = ""
    file_name: str = "script.txt"
    persona: dict[str, Any] = Field(default_factory=dict)
    glossary: dict[str, str] = Field(default_factory=dict)
    base_url: str = "http://127.0.0.1:8000/v1"
    api_key: str = ""
    model_name: str = "omlx-model"
    chunk_size: int | None = Field(default=None, ge=300, le=1800)
    translate_directives: bool = True
    persona_source: str = "auto"


class ProjectPatch(BaseModel):
    persona: dict[str, Any] | None = None
    glossary: dict[str, str] | None = None
    chunk_size: int | None = Field(default=None, ge=300, le=1800)


@dataclass
class Project:
    id: str
    request: ProjectRequest
    chunks: list[str]
    translations: list[str]
    events: queue.Queue[dict[str, Any]] = field(default_factory=queue.Queue)
    cancel: dict[str, bool] = field(default_factory=lambda: {"cancel": False})
    running: bool = False

    def snapshot(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "file_name": self.request.file_name,
            "chunks": self.chunks,
            "translations": self.translations,
            "persona": self.request.persona,
            "glossary": self.request.glossary,
            "base_url": self.request.base_url,
            "model_name": self.request.model_name,
            "chunk_size": self.request.chunk_size,
            "translate_directives": self.request.translate_directives,
            "persona_source": self.request.persona_source,
            "running": self.running,
        }


app = FastAPI(title="Persona Translator Web API", version="0.1.0")
app.mount("/static", StaticFiles(directory=WEB_DIR), name="static")
projects: dict[str, Project] = {}


def _make_client(project: Project) -> OpenAICompatClient:
    return OpenAICompatClient(
        base_url=project.request.base_url,
        api_key=project.request.api_key,
        model_name=project.request.model_name,
    )


def _chunk_script(request: ProjectRequest) -> list[str]:
    size = request.chunk_size or 900
    is_subtitle = request.file_name.lower().endswith((".srt", ".vtt", ".lrc"))
    if is_subtitle:
        return chunk_srt(request.script, target_chunk_size=size)
    return chunk_text(request.script, chunk_size=size)


def _emit(project: Project, event: dict[str, Any]) -> None:
    project.events.put(event)


def _persona_prompt(script: str, file_name: str) -> list[dict[str, str]]:
    system = """당신은 대본 전체를 읽고 번역용 캐릭터 페르소나와 일관성 규칙을 설계하는 편집자입니다.
청크 일부가 아니라 아래 대본 전체의 반복되는 말투, 화자-청자 관계, 감정 변화, 호칭, 수위와 상황 맥락을 종합해서 판단하세요.
다음 항목을 짧게 작성하세요. JSON이어도 되고 일반 텍스트여도 됩니다.
말투/어조:
화자-청자 관계:
상황:
핵심 번역 규칙:
호칭 규칙:
문체 특징:
응답은 1200 토큰 이내로 작성하고, 각 항목은 1~2문장 또는 최대 4개 목록으로 제한하세요.
근거가 약한 설정은 만들어내지 말고, 대본에서 확실히 관찰되는 내용만 적으세요."""
    user = f"[파일 형식]\n{file_name}\n\n[전체 대본]\n{script}"
    return [{"role": "system", "content": system}, {"role": "user", "content": user}]


def _analyze_persona(project: Project) -> dict[str, Any]:
    client = _make_client(project)
    response = client.generate(
        _persona_prompt(project.request.script, project.request.file_name),
        temp=0.2,
        max_tokens=2400,
    )
    raw = response.text.strip()
    try:
        persona = parse_json_response(raw)
    except (ValueError, TypeError):
        persona = {}
    if not isinstance(persona, dict):
        persona = {}
    if not persona.get("tone"):
        persona["tone"] = "원문 전체 분석 기반의 일관된 말투"
    if not persona.get("relationship"):
        persona["relationship"] = "대본의 문맥과 화자 관계를 우선하여 자연스럽게 유지"
    if not persona.get("situation"):
        persona["situation"] = raw[:4000] if raw else "전체 대본의 상황과 감정선을 유지"
    if not persona.get("key_rules"):
        persona["key_rules"] = [
            "전체 대본에서 확인되는 화자의 말투와 감정선을 일관되게 유지",
            "원문의 줄바꿈과 대본 형식을 보존",
        ]
    persona["_analysis_raw"] = raw[:8000]
    persona["_source"] = "auto"
    persona["_analyzed_model"] = project.request.model_name
    return persona


def _run_batch(project: Project) -> None:
    project.running = True
    project.cancel["cancel"] = False
    try:
        client = _make_client(project)
        if project.request.persona_source == "auto":
            _emit(project, {"type": "persona_analysis_started"})
            project.request.persona = _analyze_persona(project)
            _emit(project, {"type": "persona_analysis_completed", "persona": project.request.persona})

        def progress(token_text, index, total, current, finished):
            if finished and 0 <= index < len(project.translations):
                project.translations[index] = current
            _emit(
                project,
                {
                    "type": "chunk_progress",
                    "index": index,
                    "total": total,
                    "text": current,
                    "finished": finished,
                },
            )

        translate_script(
            client,
            None,
            project.request.script,
            project.request.persona,
            project.request.glossary,
            is_srt=project.request.file_name.lower().endswith(".srt"),
            translate_directives=project.request.translate_directives,
            chunk_size=project.request.chunk_size
            or 900,
            existing_translations=project.translations,
            cancel_token=project.cancel,
            progress_callback=progress,
            file_name=project.request.file_name,
        )
        status = "cancelled" if project.cancel.get("cancel") else "completed"
        _emit(project, {"type": status, "project": project.id})
    except Exception as exc:
        _emit(project, {"type": "error", "message": str(exc)})
    finally:
        project.running = False


def _run_persona_analysis(project: Project) -> None:
    project.running = True
    try:
        _emit(project, {"type": "persona_analysis_started"})
        persona = _analyze_persona(project)
        project.request.persona = persona
        project.request.persona_source = "auto"
        _emit(project, {"type": "persona_analysis_completed", "persona": persona})
    except Exception as exc:
        _emit(project, {"type": "error", "message": str(exc)})
    finally:
        project.running = False


def _run_single(project: Project, index: int) -> None:
    project.running = True
    try:
        client = _make_client(project)
        is_subtitle = project.request.file_name.lower().endswith((".srt", ".vtt", ".lrc"))
        previous_original = project.chunks[index - 1] if index else ""
        previous_translation = project.translations[index - 1] if index else ""
        current = project.translations[index]
        prompt_builder = build_retranslation_prompt if current.strip() else build_translation_prompt
        common = {
            "current_chunk": project.chunks[index],
            "prev_original": previous_original,
            "prev_translated": previous_translation,
            "persona": project.request.persona,
            "glossary": project.request.glossary,
            "is_srt": is_subtitle,
            "translate_directives": project.request.translate_directives,
            "file_name": project.request.file_name,
        }
        if current.strip():
            common["existing_translation"] = current
        prompt = prompt_builder(**common)

        def on_token(_token, text):
            _emit(project, {"type": "chunk_progress", "index": index, "total": len(project.chunks), "text": text, "finished": False})

        result = translate_one_chunk(
            client,
            None,
            prompt,
            cancel_token=project.cancel,
            token_callback=on_token,
        )
        if isinstance(result, tuple):
            result = result[1]
        if result:
            project.translations[index] = extract_final_translation(clean_markdown(result))
        _emit(project, {"type": "chunk_done", "index": index, "text": project.translations[index]})
    except Exception as exc:
        _emit(project, {"type": "error", "message": str(exc), "index": index})
    finally:
        project.running = False


@app.get("/")
async def index() -> FileResponse:
    return FileResponse(os.path.join(WEB_DIR, "index.html"))


@app.get("/api/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/api/projects")
async def create_project(request: ProjectRequest) -> dict[str, Any]:
    if not request.script.strip():
        raise HTTPException(status_code=400, detail="대본이 비어 있습니다.")
    if not request.chunk_size:
        request.chunk_size = 900
    chunks = _chunk_script(request)
    project = Project(str(uuid.uuid4()), request, chunks, [""] * len(chunks))
    projects[project.id] = project
    return project.snapshot()


class ConnectionRequest(BaseModel):
    base_url: str = "http://127.0.0.1:8000/v1"
    api_key: str = ""
    model_name: str = ""


@app.post("/api/connection/test")
async def test_connection(request: ConnectionRequest) -> dict[str, Any]:
    base_url = request.base_url.rstrip("/")
    headers = {"Accept": "application/json"}
    if request.api_key.strip():
        headers["Authorization"] = f"Bearer {request.api_key.strip()}"
    try:
        response = await asyncio.to_thread(
            requests.get,
            f"{base_url}/models",
            headers=headers,
            timeout=10,
        )
    except requests.RequestException as exc:
        raise HTTPException(status_code=502, detail=f"oMLX/OpenAI 호환 서버 연결 실패: {exc}") from exc

    if response.status_code >= 400:
        raise HTTPException(
            status_code=502,
            detail=f"호환 서버 오류 ({response.status_code}): {response.text[:300]}",
        )
    try:
        payload = response.json()
    except ValueError as exc:
        raise HTTPException(status_code=502, detail="서버가 JSON 모델 목록을 반환하지 않았습니다.") from exc

    model_items = [item for item in payload.get("data", []) if isinstance(item, dict)]
    models = [item.get("id") for item in model_items if item.get("id")]
    selected = request.model_name.strip()
    return {
        "status": "connected",
        "base_url": base_url,
        "models": models,
        "model_name": selected or (models[0] if models else ""),
    }


@app.get("/api/projects/{project_id}")
async def get_project(project_id: str) -> dict[str, Any]:
    project = projects.get(project_id)
    if not project:
        raise HTTPException(status_code=404, detail="프로젝트를 찾을 수 없습니다.")
    return project.snapshot()


@app.patch("/api/projects/{project_id}")
async def patch_project(project_id: str, patch: ProjectPatch) -> dict[str, Any]:
    project = projects.get(project_id)
    if not project:
        raise HTTPException(status_code=404, detail="프로젝트를 찾을 수 없습니다.")
    if project.running:
        raise HTTPException(status_code=409, detail="번역 중에는 설정을 변경할 수 없습니다.")
    if patch.persona is not None:
        project.request.persona = patch.persona
        project.request.persona_source = "manual"
    if patch.glossary is not None:
        project.request.glossary = patch.glossary
    if patch.chunk_size is not None and patch.chunk_size != project.request.chunk_size:
        project.request.chunk_size = patch.chunk_size
        project.chunks = _chunk_script(project.request)
        project.translations = [""] * len(project.chunks)
    return project.snapshot()


@app.post("/api/projects/{project_id}/translate")
async def start_translation(project_id: str) -> dict[str, str]:
    project = projects.get(project_id)
    if not project:
        raise HTTPException(status_code=404, detail="프로젝트를 찾을 수 없습니다.")
    if project.running:
        raise HTTPException(status_code=409, detail="이미 번역 중입니다.")
    EXECUTOR.submit(_run_batch, project)
    return {"status": "started"}


@app.post("/api/projects/{project_id}/analyze-persona")
async def analyze_persona(project_id: str) -> dict[str, str]:
    project = projects.get(project_id)
    if not project:
        raise HTTPException(status_code=404, detail="프로젝트를 찾을 수 없습니다.")
    if project.running:
        raise HTTPException(status_code=409, detail="이미 다른 작업이 실행 중입니다.")
    EXECUTOR.submit(_run_persona_analysis, project)
    return {"status": "started"}


@app.post("/api/projects/{project_id}/chunks/{index}/translate")
async def translate_chunk(project_id: str, index: int) -> dict[str, str]:
    project = projects.get(project_id)
    if not project:
        raise HTTPException(status_code=404, detail="프로젝트를 찾을 수 없습니다.")
    if project.running:
        raise HTTPException(status_code=409, detail="다른 번역 작업이 실행 중입니다.")
    if index < 0 or index >= len(project.chunks):
        raise HTTPException(status_code=404, detail="청크를 찾을 수 없습니다.")
    EXECUTOR.submit(_run_single, project, index)
    return {"status": "started", "index": str(index)}


@app.post("/api/projects/{project_id}/cancel")
async def cancel_translation(project_id: str) -> dict[str, str]:
    project = projects.get(project_id)
    if not project:
        raise HTTPException(status_code=404, detail="프로젝트를 찾을 수 없습니다.")
    project.cancel["cancel"] = True
    return {"status": "cancelling"}


@app.get("/api/projects/{project_id}/events")
async def project_events(project_id: str) -> StreamingResponse:
    project = projects.get(project_id)
    if not project:
        raise HTTPException(status_code=404, detail="프로젝트를 찾을 수 없습니다.")

    async def stream():
        while True:
            try:
                event = await asyncio.to_thread(project.events.get, True, 15)
                yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"
                if event["type"] in {"completed", "error"}:
                    break
            except queue.Empty:
                yield ": keep-alive\n\n"

    return StreamingResponse(stream(), media_type="text/event-stream")
