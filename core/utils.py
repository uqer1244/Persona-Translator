import os
import re
import atexit
import streamlit as st
from core.progress_store import (
    get_backup_dir,
    get_backup_path,
    list_saved_images,
    load_progress,
    save_progress,
)

_RUNTIME_CLEANED_UP = False
_SIGNAL_HANDLERS_INSTALLED = False

# 글로벌 단일 스레드 Executor를 Streamlit resource 캐싱을 통해 싱글톤으로 유지
@st.cache_resource
def get_executor():
    from concurrent.futures import ThreadPoolExecutor
    return ThreadPoolExecutor(max_workers=1)

EXECUTOR = get_executor()


def _clear_mlx_runtime():
    try:
        import gc
        import mlx.core as mx

        mx.clear_cache()
        gc.collect()
    except Exception:
        pass


def cleanup_runtime_resources(shutdown_executor: bool = False):
    global _RUNTIME_CLEANED_UP
    if _RUNTIME_CLEANED_UP:
        return

    try:
        load_model_cached.clear()
    except Exception:
        pass

    _clear_mlx_runtime()

    if shutdown_executor:
        try:
            EXECUTOR.shutdown(wait=False, cancel_futures=True)
        except Exception:
            pass

    _RUNTIME_CLEANED_UP = True


def _install_shutdown_hooks():
    global _SIGNAL_HANDLERS_INSTALLED
    if _SIGNAL_HANDLERS_INSTALLED:
        return

    atexit.register(lambda: cleanup_runtime_resources(shutdown_executor=True))

    try:
        import signal
        import sys

        previous_handlers = {
            signal.SIGINT: signal.getsignal(signal.SIGINT),
            signal.SIGTERM: signal.getsignal(signal.SIGTERM),
        }

        def handle_shutdown(signum, frame):
            cleanup_runtime_resources(shutdown_executor=True)
            previous = previous_handlers.get(signum)
            if callable(previous):
                previous(signum, frame)
            elif signum == signal.SIGINT:
                raise KeyboardInterrupt
            else:
                sys.exit(0)

        signal.signal(signal.SIGINT, handle_shutdown)
        signal.signal(signal.SIGTERM, handle_shutdown)
    except Exception:
        pass

    _SIGNAL_HANDLERS_INSTALLED = True


_install_shutdown_hooks()

class LiveStatus:
    def __init__(self):
        self.current_chunk_idx = -1
        self.current_streaming_text = ""
        self.completed_translations = {}        # idx -> clean_translation
        self.single_streaming_text = {}        # idx -> str
        self.single_completed_translations = {} # idx -> clean_translation

def colorize_directives(text: str) -> str:
    """
    대본에서 괄호 지시문 및 의성어/의태어 형태의 텍스트(예: [whispering], (한숨), *giggles*)를 감지하여
    HTML span 태그를 통해 색상을 입혀 반환합니다.
    """
    if not text:
        return ""
    # HTML 특수기호 안전 처리 (이스케이프)
    text = text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    
    # 1. 대괄호 [속삭임], [whispering] -> 파스텔 오렌지 (#ffb86c)
    text = re.sub(r'(\[[^\]\n]+\])', r'<span style="color: #ffb86c; font-weight: bold;">\1</span>', text)
    
    # 2. 소괄호 (한숨), (sighs) -> 파스텔 핑크 (#ff79c6)
    text = re.sub(r'(\([^)\n]+\))', r'<span style="color: #ff79c6; font-style: italic;">\1</span>', text)
    
    # 3. 별표 *소곤소곤*, *giggles* -> 파스텔 민트/하늘 (#8be9fd)
    text = re.sub(r'(\*[^*\n]+\*)', r'<span style="color: #8be9fd; font-style: italic;">\1</span>', text)
    
    # 4. SRT 타임라인 (00:00:01,000 --> 00:00:04,000) -> 흐린 회색 (#6272a4)
    text = re.sub(r'(\d{2}:\d{2}:\d{2}[,.]\d{3}\s*-->\s*\d{2}:\d{2}:\d{2}[,.]\d{3})', r'<span style="color: #6272a4; font-size: 12px; font-family: monospace;">\1</span>', text)
    
    return text

def save_progress_backup():
    if "file_name" not in st.session_state or not st.session_state.file_name or "chunks" not in st.session_state or not st.session_state.chunks:
        return
    save_progress(
        st.session_state.file_name,
        st.session_state.chunks,
        st.session_state.translated_chunks,
    )

def load_progress_backup(file_name: str) -> bool:
    try:
        data = load_progress(file_name)
        if data:
            # 청크 개수가 일치하는 경우에만 이전 번역 불러오기 진행
            if len(data.get("original_chunks", [])) == len(st.session_state.chunks):
                st.session_state.translated_chunks = data.get("translated_chunks", [])
                
                # 백업 데이터 불러올 때 각 청크별 위젯 세션 상태와 전체 번역본 동기화
                is_srt = file_name.endswith(".srt")
                if is_srt:
                    st.session_state.translated_script = "\n\n".join([c for c in st.session_state.translated_chunks if c])
                else:
                    st.session_state.translated_script = "\n".join([c for c in st.session_state.translated_chunks if c])
                
                for idx, val in enumerate(st.session_state.translated_chunks):
                    st.session_state[f"chunk_trans_{idx}"] = val
                
                st.session_state.temp_image_paths = list_saved_images(file_name)
                return True
    except Exception:
        pass
    return False

def sync_chunks(chunk_size):
    if not st.session_state.original_script.strip():
        # 기존 청크 관련 위젯 상태 삭제
        for idx in range(len(st.session_state.chunks)):
            key = f"chunk_trans_{idx}"
            if key in st.session_state:
                del st.session_state[key]
        st.session_state.chunks = []
        st.session_state.translated_chunks = []
        st.session_state.translated_script = ""
        return
        
    from core.translator import chunk_text, chunk_srt
    is_srt = st.session_state.file_name.endswith(".srt")
    if is_srt:
        new_chunks = chunk_srt(st.session_state.original_script)
    else:
        new_chunks = chunk_text(st.session_state.original_script, chunk_size=chunk_size)
        
    if st.session_state.chunks != new_chunks:
        # 기존의 청크 개수만큼 저장되어 있던 세션 상태 위젯 키 제거
        for idx in range(len(st.session_state.chunks)):
            key = f"chunk_trans_{idx}"
            if key in st.session_state:
                del st.session_state[key]
                
        st.session_state.chunks = new_chunks
        st.session_state.translated_chunks = [""] * len(new_chunks)
        st.session_state.translated_script = ""
        # 로컬 백업이 존재하면 이어서 번역할 수 있도록 로드 시도
        load_progress_backup(st.session_state.file_name)

# Lazy loading model
@st.cache_resource
def load_model_cached(model_path: str):
    def _load():
        import mlx.core as mx
        import gc
        # 로딩 전 메모리 비우기
        mx.clear_cache()
        gc.collect()
        
        # 메탈 캐시 한계를 0으로 설정하여 캐시 메모리 즉시 반환 유도
        mx.set_cache_limit(0)
        
        from mlx_vlm import load
        model, processor = load(model_path)
        
        # 로딩 후 정리
        mx.clear_cache()
        gc.collect()
        return model, processor
    
    # MLX 가동용 단일 스레드 스레드풀에서 모델 로드 실행
    future = EXECUTOR.submit(_load)
    return future.result()


def unload_model():
    st.session_state.model = None
    st.session_state.processor = None
    st.session_state.model_loaded = False
    try:
        load_model_cached.clear()
    except Exception:
        pass
    _clear_mlx_runtime()

def extract_script_structure(script: str, file_name: str = "", max_chars_per_track: int = 1200, max_total_chars: int = 8000) -> str:
    if not script:
        return ""
        
    # SRT 파일명이거나 본문 내에 SRT 타임라인 화살표(-->)가 있는 경우, 자막 인덱스 숫자가 트랙으로 오진되는 것을 방지
    is_srt = file_name.lower().endswith(".srt") or "-->" in script
    
    if is_srt:
        return script[:max_total_chars]
        
    # 트랙 구분을 식별하기 위한 정규식 패턴 정의 (단순 줄번호 1., 2. 등은 제외하고 트랙 키워드나 오디오 확장자, leading zero만 매칭)
    track_pattern = re.compile(
        r'^\s*(?:'
        r'(?:[tT]rack|[tT]RACK|트랙|part|파트|scene|씬|#)\s*\d+'
        r'|\[\s*(?:[tT]rack|[tT]RACK|트랙|part|파트|scene|씬)\s*\d+\s*\]'
        r'|0\d\s*(?:[\.\:\-\_]|\n|$)'
        r'|\d{1,2}\s*(?:\.wav|\.mp3|\.txt|\.m4a)\b'
        r')\s*(?:[\.\:\-\_]|\n|$)',
        re.MULTILINE
    )
    
    matches = list(track_pattern.finditer(script))
    
    # 감지된 트랙이 1개 이하일 경우 구조화의 실익이 없으므로 단순 슬라이싱 반환
    if len(matches) <= 1:
        return script[:max_total_chars]
        
    # 각 매칭된 트랙 경계를 기준으로 세그먼트 생성
    segments = []
    num_matches = len(matches)
    for idx, match in enumerate(matches):
        start_idx = match.start()
        end_idx = matches[idx+1].start() if idx + 1 < num_matches else len(script)
        segment_content = script[start_idx:end_idx].strip()
        segments.append(segment_content)
        
    # 트랙별 캐릭터 심리나 전개 분석을 위해 각 트랙당 배정할 글자 수 예산 책정
    char_budget_per_track = max(500, max_total_chars // len(segments))
    char_limit = min(max_chars_per_track, char_budget_per_track)
    
    structured_parts = []
    for i, seg in enumerate(segments):
        if len(seg) > char_limit:
            # 트랙의 전반부를 예산 크기만큼 취하고 생략 표시 추가
            truncated_seg = seg[:char_limit].strip() + "\n... (이하 생략) ..."
        else:
            truncated_seg = seg
        structured_parts.append(f"--- [트랙 {i+1} 상세 본문] ---\n{truncated_seg}")
        
    result = "\n\n".join(structured_parts)
    # VRAM OOM 안전을 위한 최종 글자수 강제 절단
    if len(result) > max_total_chars:
        result = result[:max_total_chars] + "\n... (전체 본문 제한으로 뒷부분 생략) ..."
    return result
