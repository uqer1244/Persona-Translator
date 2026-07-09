import os
import json
import urllib.parse
from fastapi import FastAPI, Request, Query, HTTPException
from fastapi.responses import HTMLResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel
from core.chat_engine import ChatEngine
from core.progress_store import BACKUP_ROOT, list_saved_personas

# FastAPI application initialization
app = FastAPI(
    title="PersonaASMR-Chat Extension",
    description="ASMR Roleplay Chat Web Interface powered by mlx_vlm"
)

# Ensure directories exist
os.makedirs("./static/css", exist_ok=True)
os.makedirs("./static/js", exist_ok=True)
os.makedirs("./templates", exist_ok=True)

# Mount static files and templates
app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")

# Instanciate global ChatEngine
chat_engine = ChatEngine()


class LoadProjectRequest(BaseModel):
    project_name: str
    model_path: str = ""


@app.get("/", response_class=HTMLResponse)
async def get_index(request: Request):
    """
    AI 롤플레잉 익스텐션 웹페이지 홈 렌더링
    """
    return templates.TemplateResponse(request=request, name="chat.html", context={})


@app.get("/api/projects")
async def get_projects():
    """
    기존 번역 완료된 백업 프로젝트 폴더 목록을 반환합니다.
    """
    try:
        projects = list_saved_personas()
        return {"projects": projects}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/models")
async def get_models():
    """
    models/ 폴더 내에 존재하는 로컬 MLX VLM 모델 폴더 리스트를 검출하여 반환합니다.
    """
    models_root = "./models"
    if not os.path.exists(models_root):
        return {"models": []}

    models = []
    for d in os.listdir(models_root):
        dir_path = os.path.join(models_root, d)
        if os.path.isdir(dir_path) and not d.startswith("."):
            # config.json이 존재하는 디렉토리만 유효 모델로 판단
            if os.path.exists(os.path.join(dir_path, "config.json")):
                models.append(os.path.abspath(dir_path))
    return {"models": models}


@app.post("/api/projects/load")
async def load_project(req: LoadProjectRequest):
    """
    사용자가 선택한 번역 프로젝트의 페르소나/대본 정보를 RAG 메모리에 로드하고,
    필요시 로컬 MLX 모델을 VRAM에 초기 적재합니다.
    """
    try:
        # 1. RAG 및 페르소나 설정 로드
        chat_engine.load_project(req.project_name)

        # 2. 모델 경로 결정
        model_path = req.model_path.strip()
        if not model_path:
            # model_path 지정 안 될 시, models/ 폴더 내 첫 번째 모델 선택 (자동 탐색)
            models_resp = await get_models()
            available_models = models_resp.get("models", [])
            if available_models:
                model_path = available_models[0]
            else:
                return {
                    "status": "warning",
                    "message": f"Project '{req.project_name}' loaded, but no local MLX VLM model was found under ./models. Please install a model or pass a path."
                }

        # 3. 모델 메모리 적재 및 중복 로드 방지
        if chat_engine.model_loaded and chat_engine.model_path == model_path:
            print("[app_chat] Model already loaded. Skipping redundant load.")
        else:
            if chat_engine.model_loaded:
                chat_engine.unload_model()
            chat_engine.load_model(model_path)

        return {
            "status": "success",
            "message": f"Project '{req.project_name}' and MLX Model loaded successfully.",
            "persona": chat_engine.persona,
            "glossary": chat_engine.glossary_list
        }
    except Exception as e:
        print(f"[app_chat ERROR] Failed to load project: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/chat/stream")
async def chat_stream(
    user_message: str = Query(..., description="User chat message"),
    history: str = Query("[]", description="URL encoded JSON chat history array")
):
    """
    Server-Sent Events(SSE) 규격을 따르는 실시간 비동기 스트리밍 대답 전송 API
    """
    if not chat_engine.model_loaded:
        raise HTTPException(status_code=400, detail="VLM model not loaded. Please load a project first.")

    try:
        decoded_history = urllib.parse.unquote(history)
        history_list = json.loads(decoded_history)
    except Exception:
        history_list = []

    def sse_generator():
        # chat_engine에서 나오는 JSON 텍스트 청크를 SSE 'data: ' 스펙으로 포장
        for chunk in chat_engine.generate_chat_response_stream(user_message, history_list):
            yield f"data: {chunk}\n"

    return StreamingResponse(sse_generator(), media_type="text/event-stream")


@app.post("/api/chat/unload")
async def unload_model():
    """
    VRAM 자원 고갈을 막기 위해 가동 중인 모델 자원을 즉시 회수합니다.
    """
    try:
        chat_engine.unload_model()
        return {"status": "success", "message": "MLX VLM model unloaded from Metal VRAM."}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
