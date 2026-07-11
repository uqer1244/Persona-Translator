import os
import re
import atexit
import streamlit as st
from core.progress_store import (
    load_persona_backup,
    save_persona_backup,
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


def natural_sort_key(s: str) -> list:
    """
    Sort key function for natural sorting (e.g. track1, track2, track10).
    """
    return [int(text) if text.isdigit() else text.lower() for text in re.split(r"(\d+)", s)]


def decode_text(raw_data: bytes) -> str:
    """
    Decodes raw bytes into a string by trying common encodings and falling back to UTF-8 with replacement.
    """
    # 1. Try UTF-8 (with BOM check)
    try:
        return raw_data.decode("utf-8-sig")
    except UnicodeDecodeError:
        pass

    # 2. Try Shift_JIS / CP932 (Japanese ASMR scripts)
    try:
        return raw_data.decode("cp932")
    except UnicodeDecodeError:
        pass

    # 3. Try CP949 / EUC-KR (Korean)
    try:
        return raw_data.decode("cp949")
    except UnicodeDecodeError:
        pass

    # 4. Try UTF-16
    try:
        return raw_data.decode("utf-16")
    except UnicodeDecodeError:
        pass

    # 5. Robust fallback: UTF-8 with errors replaced, avoiding complete mojibake from latin1
    return raw_data.decode("utf-8", errors="replace")


def has_repetition(text: str) -> bool:
    """
    체크할 텍스트 뒷부분에서 중복되는 패턴이 연속으로 발생하는지 감지합니다.
    """
    if len(text) < 15:
        return False
        
    # 최근 200자만 검사
    text_to_check = text[-200:]
    
    # 1. 단어/구절 단위 반복 감지 (예: "밑에 눈 밑에 눈 밑에 눈")
    # 짧은 길이(2자)부터 긴 길이(40자)까지 패턴 매칭
    for pattern_len in range(2, 40):
        required_repeats = 4 if pattern_len < 5 else 3
        if len(text_to_check) < pattern_len * required_repeats:
            continue
        pattern = text_to_check[-pattern_len:]
        
        # 공백이나 문장부호로만 이루어진 패턴은 감지에서 제외
        if not pattern.strip() or all(c in " .,!?\n*()[]_-" for c in pattern):
            continue
            
        if text_to_check.endswith(pattern * required_repeats):
            return True
            
    # 2. 개별 문자 반복 감지 (예: "눈눈눈눈눈눈눈눈")
    if len(text_to_check) >= 8:
        last_char = text_to_check[-1]
        if last_char not in (" ", "\n", ".", "-", "*", "~", ","):
            if text_to_check[-8:] == last_char * 8:
                return True
                
    return False


def strip_repetition(text: str) -> str:
    """
    텍스트 뒷부분에서 발생하는 중복 반복 구간을 제거하여, 1회만 노출되도록 정리한 텍스트를 반환합니다.
    """
    if len(text) < 15:
        return text
        
    text_to_check = text[-200:]
    
    # 1. 단어/구절 단위 반복 감지 및 제거
    for pattern_len in range(2, 40):
        required_repeats = 4 if pattern_len < 5 else 3
        if len(text_to_check) < pattern_len * required_repeats:
            continue
        pattern = text_to_check[-pattern_len:]
        
        if not pattern.strip() or all(c in " .,!?\n*()[]_-" for c in pattern):
            continue
            
        if text_to_check.endswith(pattern * required_repeats):
            redundant_len = pattern_len * (required_repeats - 1)
            if len(text) >= redundant_len:
                return text[:-redundant_len]
            
    # 2. 개별 문자 반복 감지 및 제거
    if len(text_to_check) >= 8:
        last_char = text_to_check[-1]
        if last_char not in (" ", "\n", ".", "-", "*", "~", ","):
            if text_to_check[-8:] == last_char * 8:
                redundant_len = 6 # 8개 중 6개 삭제하여 2개만 유지
                if len(text) >= redundant_len:
                    return text[:-redundant_len]
                
    return text



# Note: Model management resources and shutdown hooks are now initialized in core.model_manager

class LiveStatus:
    def __init__(self):
        self.current_chunk_idx = -1
        self.current_streaming_text = ""
        self.completed_translations = {}        # idx -> clean_translation
        self.single_streaming_text = {}        # idx -> str
        self.single_completed_translations = {} # idx -> clean_translation

def colorize_directives(text: str) -> str:
    """
    대본에서 괄호 지시문, 의성어/의태어, 타임라인 및 등장인물의 대사 접두어를 감지하여
    HTML span 태그를 통해 서로 다른 파스텔 색상을 입혀 반환합니다.
    """
    if not text:
        return ""
    # HTML 특수기호 안전 처리 (이스케이프)
    text = text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    
    # 1. 등장인물 이름 감지 및 일관성 있는 색상 맵 매핑
    lines = text.split("\n")
    unique_chars = set()
    char_pattern = re.compile(r'^\s*([^:\s\n()[\]*?［］（）「」『』＊]{1,10})\s*([:：]|[「『])')
    
    for line in lines:
        match = char_pattern.match(line)
        if match:
            char_name = match.group(1).strip()
            # 숫자로만 이루어져 있거나 시간 정보(예: 00)인 경우는 제외
            if char_name and not char_name.isdigit() and len(char_name) > 0:
                lower_name = char_name.lower()
                # 트랙이나 씬 구분 식별자 제외
                if any(k in lower_name for k in ("track", "part", "scene", "episode", "씬", "트랙", "파트")):
                    continue
                unique_chars.add(char_name)
                
    # 일관된 컬러 선택을 위한 알파벳 순 정렬
    sorted_chars = sorted(list(unique_chars))
    
    # 프리미엄 파스텔 컬러 리스트 (다크 모드 가독성 고려)
    char_colors = [
        "#50fa7b", # 연두색
        "#bd93f9", # 보라색
        "#f1fa8c", # 노란색
        "#ff5555", # 빨간색
        "#8be9fd", # 하늘색
        "#ff79c6", # 분홍색
        "#ffb86c", # 주황색
    ]
    
    char_color_map = {}
    for idx, char_name in enumerate(sorted_chars):
        char_color_map[char_name] = char_colors[idx % len(char_colors)]
        
    # 캐릭터 이름 색상화 적용
    for i, line in enumerate(lines):
        match = char_pattern.match(line)
        if match:
            char_name = match.group(1).strip()
            if char_name in char_color_map:
                color = char_color_map[char_name]
                delimiter = match.group(2) # 콜론 기호 (: 또는 ：) 또는 따옴표 기호 (「 또는 『)
                replacement = f'<span style="color: {color}; font-weight: bold;">{char_name}</span>{delimiter}'
                lines[i] = replacement + line[match.end():]
                
    text = "\n".join(lines)
    
    # 2. 대괄호 [속삭임], [whispering], ［속삭임］ -> 파스텔 오렌지 (#ffb86c)
    text = re.sub(r'([\[［][^\]］\n]+[\]］])', r'<span style="color: #ffb86c; font-weight: bold;">\1</span>', text)
    
    # 3. 소괄호 (한숨), (sighs), （한숨） -> 파스텔 핑크 (#ff79c6)
    text = re.sub(r'([\([（][^)）\n]+[\)）])', r'<span style="color: #ff79c6; font-style: italic;">\1</span>', text)
    
    # 4. 별표 *소곤소곤*, *giggles*, ＊소곤소곤＊ -> 파스텔 민트/하늘 (#8be9fd)
    text = re.sub(r'([\*＊][^*＊\n]+[\*＊])', r'<span style="color: #8be9fd; font-style: italic;">\1</span>', text)
    
    # 5. SRT 타임라인 (00:00:01,000 --> 00:00:04,000) -> 흐린 회색 (#6272a4)
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
                raw_trans = data.get("translated_chunks", [])
                st.session_state.translated_chunks = [c if isinstance(c, str) else "" for c in raw_trans]
                
                # 백업 데이터 불러올 때 각 청크별 위젯 세션 상태와 전체 번역본 동기화
                is_srt = file_name.endswith(".srt")
                if is_srt:
                    st.session_state.translated_script = "\n\n".join([c for c in st.session_state.translated_chunks if c])
                else:
                    st.session_state.translated_script = "\n".join([c for c in st.session_state.translated_chunks if c])
                
                for idx, val in enumerate(st.session_state.translated_chunks):
                    st.session_state[f"chunk_trans_{idx}"] = val
                
                st.session_state.temp_image_paths = list_saved_images(file_name)
                
                # 페르소나 및 용어집 개별 백업 로드
                p_data = load_persona_backup(file_name)
                if p_data:
                    if "persona" in p_data and p_data["persona"]:
                        st.session_state.persona = p_data["persona"]
                    if "glossary_data" in p_data and p_data["glossary_data"]:
                        st.session_state.glossary_data = p_data["glossary_data"]
                        
                return True
    except Exception:
        pass

    # 백업 로드가 실패했거나 데이터가 없는 최초 상황인 경우:
    # 대본 입력이 완료되어 있으면 AI 채팅 탭 등 다른 화면에서 즉시 프로젝트를 로드할 수 있도록
    # 최초 progress.json과 persona.json 파일을 생성해 줍니다.
    if "original_script" in st.session_state and st.session_state.original_script.strip() and "chunks" in st.session_state and st.session_state.chunks:
        try:
            from core.progress_store import save_progress, save_persona_backup
            save_progress(
                file_name,
                st.session_state.chunks,
                st.session_state.translated_chunks
            )
            save_persona_backup(
                file_name,
                st.session_state.persona,
                st.session_state.glossary_data
            )
        except Exception as e:
            print(f"[load_progress_backup] 최초 백업 파일 생성 실패: {e}")
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
        new_chunks = chunk_srt(st.session_state.original_script, target_chunk_size=chunk_size)
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

from core.model_manager import load_model_cached, unload_model

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


def trigger_streamlit_rerun(ctx):
    """
    백그라운드 스레드에서 Streamlit 메인 세션 재실행(Rerun)을 트리거합니다.
    """
    if not ctx:
        return
    try:
        from streamlit.runtime import get_instance
        runtime = get_instance()
        session_info = runtime._session_mgr.get_active_session_info(ctx.session_id)
        if session_info:
            session_info.session.request_rerun(None)
    except Exception:
        pass


def get_memory_stats():
    """
    시스템 RAM 및 Apple Silicon Unified GPU 메모리 점유율을 바이트 단위에서 GB 단위로 변환해 반환합니다.
    """
    import psutil
    import mlx.core as mx

    # 1. System RAM
    try:
        vm = psutil.virtual_memory()
        ram_used = vm.used / (1024**3)
        ram_total = vm.total / (1024**3)
        ram_percent = vm.percent
    except Exception:
        ram_used, ram_total, ram_percent = 0.0, 0.0, 0.0

    # 2. MLX metal Memory (Unified GPU Memory)
    try:
        active_mem = mx.get_active_memory() / (1024**3)
        peak_mem = mx.get_peak_memory() / (1024**3)
        cache_mem = mx.get_cache_memory() / (1024**3)
    except Exception:
        try:
            active_mem = mx.metal.get_active_memory() / (1024**3)
            peak_mem = mx.metal.get_peak_memory() / (1024**3)
            cache_mem = mx.metal.get_cache_memory() / (1024**3)
        except Exception:
            active_mem, peak_mem, cache_mem = 0.0, 0.0, 0.0

    return {
        "ram_used_gb": ram_used,
        "ram_total_gb": ram_total,
        "ram_percent": ram_percent,
        "mlx_active_gb": active_mem,
        "mlx_peak_gb": peak_mem,
        "mlx_cache_gb": cache_mem
    }

