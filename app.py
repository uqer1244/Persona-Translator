import streamlit as st
import os
import re
import pandas as pd
import json

# 글로벌 단일 스레드 Executor를 Streamlit resource 캐싱을 통해 싱글톤으로 유지
@st.cache_resource
def get_executor():
    from concurrent.futures import ThreadPoolExecutor
    return ThreadPoolExecutor(max_workers=1)

EXECUTOR = get_executor()

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


def get_backup_dir(file_name: str) -> str:
    backup_root = os.path.abspath("./temp_backups")
    base_name, _ = os.path.splitext(file_name)
    safe_name = re.sub(r'[^a-zA-Z0-9_\-]', '_', base_name)
    project_dir = os.path.join(backup_root, safe_name)
    os.makedirs(project_dir, exist_ok=True)
    return project_dir

def get_backup_path(file_name: str) -> str:
    project_dir = get_backup_dir(file_name)
    return os.path.join(project_dir, "progress.json")

def save_progress_backup():
    if "file_name" not in st.session_state or not st.session_state.file_name or "chunks" not in st.session_state or not st.session_state.chunks:
        return
    backup_path = get_backup_path(st.session_state.file_name)
    data = {
        "file_name": st.session_state.file_name,
        "original_chunks": st.session_state.chunks,
        "translated_chunks": st.session_state.translated_chunks,
    }
    with open(backup_path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

def load_progress_backup(file_name: str) -> bool:
    backup_path = get_backup_path(file_name)
    if os.path.exists(backup_path):
        try:
            with open(backup_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            # 청크 개수가 일치하는 경우에만 이전 번역 불러오기 진행
            if len(data.get("original_chunks", [])) == len(st.session_state.chunks):
                st.session_state.translated_chunks = data.get("translated_chunks", [])
                
                # 백업 폴더 내부의 이미지 디렉토리 조회 및 로드
                project_dir = get_backup_dir(file_name)
                images_dir = os.path.join(project_dir, "images")
                if os.path.exists(images_dir):
                    saved_images = [os.path.join(images_dir, f) for f in os.listdir(images_dir) if not f.startswith(".")]
                    saved_images.sort()
                    st.session_state.temp_image_paths = saved_images
                else:
                    st.session_state.temp_image_paths = []
                return True
        except Exception:
            pass
    return False

def sync_chunks(chunk_size):
    if not st.session_state.original_script.strip():
        st.session_state.chunks = []
        st.session_state.translated_chunks = []
        return
        
    from core.translator import chunk_text, chunk_srt
    is_srt = st.session_state.file_name.endswith(".srt")
    if is_srt:
        new_chunks = chunk_srt(st.session_state.original_script)
    else:
        new_chunks = chunk_text(st.session_state.original_script, chunk_size=chunk_size)
        
    if st.session_state.chunks != new_chunks:
        st.session_state.chunks = new_chunks
        st.session_state.translated_chunks = [""] * len(new_chunks)
        # 로컬 백업이 존재하면 이어서 번역할 수 있도록 로드 시도
        load_progress_backup(st.session_state.file_name)




# Local models directory
MODELS_DIR = os.path.abspath("./models")
os.makedirs(MODELS_DIR, exist_ok=True)

# Page configuration
st.set_page_config(
    page_title="PersonaASMR-Translator",
    page_icon=None,
    layout="wide",
    initial_sidebar_state="expanded"
)

# Custom CSS for UI styling
st.markdown("""
<style>
    .stTabs [data-baseweb="tab-list"] {
        gap: 12px;
    }
    .stTabs [data-baseweb="tab"] {
        height: 48px;
        white-space: pre-wrap;
        background-color: #1e293b;
        border-radius: 6px 6px 0px 0px;
        padding: 10px 16px;
        color: #94a3b8;
        font-weight: 500;
        transition: all 0.2s ease;
    }
    .stTabs [aria-selected="true"] {
        background-color: #0f172a;
        color: #38bdf8 !important;
        font-weight: 700;
        border-bottom: 2px solid #38bdf8;
    }
    .card {
        background-color: #1e293b;
        padding: 20px;
        border-radius: 8px;
        border: 1px solid #334155;
        margin-bottom: 15px;
    }
    .status-box {
        padding: 12px;
        border-radius: 6px;
        margin-bottom: 12px;
        font-weight: bold;
    }
    .status-ok {
        background-color: #064e3b;
        color: #34d399;
        border: 1px solid #059669;
    }
    .status-warn {
        background-color: #78350f;
        color: #fbbf24;
        border: 1px solid #d97706;
    }
</style>
""", unsafe_allow_html=True)

# Session state initialization
if "model_loaded" not in st.session_state:
    st.session_state.model_loaded = False
if "model" not in st.session_state:
    st.session_state.model = None
if "processor" not in st.session_state:
    st.session_state.processor = None
if "persona" not in st.session_state:
    st.session_state.persona = {
        "tone": "",
        "relationship": "",
        "key_rules": []
    }
if "original_script" not in st.session_state:
    st.session_state.original_script = ""
if "metadata_text" not in st.session_state:
    st.session_state.metadata_text = ""
if "translated_script" not in st.session_state:
    st.session_state.translated_script = ""
if "glossary_data" not in st.session_state:
    st.session_state.glossary_data = []
if "file_name" not in st.session_state:
    st.session_state.file_name = "script.txt"
if "temp_image_paths" not in st.session_state:
    st.session_state.temp_image_paths = []
if "script_summary" not in st.session_state:
    st.session_state.script_summary = {
        "speaker_name": "미분석",
        "listener_role": "미분석",
        "situation": "대본 분석 전입니다.",
        "story": "대본 분석 전입니다."
    }
if "chunks" not in st.session_state:
    st.session_state.chunks = []
if "translated_chunks" not in st.session_state:
    st.session_state.translated_chunks = []


# Lazy loading model
@st.cache_resource
def load_model_cached(model_path: str):
    def _load():
        import mlx.core as mx
        import gc
        # 로딩 전 메모리 비우기
        mx.metal.clear_cache()
        gc.collect()
        
        # 메탈 캐시 한계를 0으로 설정하여 캐시 메모리 즉시 반환 유도
        mx.metal.set_cache_limit(0)
        
        from mlx_vlm import load
        model, processor = load(model_path)
        
        # 로딩 후 정리
        mx.metal.clear_cache()
        gc.collect()
        return model, processor
    
    # MLX 가동용 단일 스레드 스레드풀에서 모델 로드 실행
    future = EXECUTOR.submit(_load)
    return future.result()

# Main Title
st.title("PersonaASMR-Translator")
st.markdown("로컬 MLX VLM (Gemma 4 12B) 기반 NSFW ASMR 맞춤형 페르소나 번역 시스템")

# Sidebar Configuration
with st.sidebar:
    st.header("시스템 설정")
    st.markdown(f"**추론 엔진**: `mlx-vlm`")
    
    # Scan for local model subdirectories in ./models/
    local_models = []
    if os.path.exists(MODELS_DIR):
        for d in os.listdir(MODELS_DIR):
            full_path = os.path.join(MODELS_DIR, d)
            if os.path.isdir(full_path) and d != "hf_cache" and not d.startswith("."):
                local_models.append(os.path.join("models", d))
                
    # Model Selection UI
    options = local_models + ["직접 경로 입력..."]
    selected_option = st.selectbox(
        "로컬 모델 선택",
        options=options,
        index=0 if local_models else len(options)-1
    )
    
    if selected_option == "직접 경로 입력...":
        model_path = st.text_input(
            "모델 폴더 절대 경로 또는 Hugging Face ID", 
            value=os.path.abspath("./models/gemma-4-12B-it-8bit")
        )
    else:
        model_path = os.path.abspath(selected_option)
        
    st.markdown(f"**로드할 경로**: `{model_path}`")
    
    # Model load button
    if not st.session_state.model_loaded:
        st.markdown('<div class="status-box status-warn">모델 로드 필요</div>', unsafe_allow_html=True)
        if st.button("로컬 모델 메모리에 로딩", use_container_width=True):
            if not os.path.exists(model_path) and not "/" in model_path:
                st.error("지정한 로컬 경로가 존재하지 않습니다. 올바른 경로를 입력해 주세요.")
            else:
                try:
                    with st.spinner("지정한 경로에서 모델을 불러오는 중입니다..."):
                        model, processor = load_model_cached(model_path)
                        st.session_state.model = model
                        st.session_state.processor = processor
                        st.session_state.model_loaded = True
                    st.success("모델 로드 성공!")
                    st.rerun()
                except Exception as e:
                    st.error(f"모델 로드 중 오류 발생: {e}")
    else:
        st.markdown('<div class="status-box status-ok">모델 준비 완료</div>', unsafe_allow_html=True)
        st.info(f"현재 로드된 모델: {model_path}")
        if st.button("모델 메모리 재로딩", use_container_width=True):
            st.session_state.model_loaded = False
            st.rerun()
            
    st.divider()
    
    # Translation parameters
    st.header("하이퍼파라미터")
    temperature = st.slider("Temperature (창의성/자유도)", 0.1, 1.0, 0.3, step=0.1)
    repetition_penalty = st.slider("Repetition Penalty (반복 억제력)", 1.0, 1.5, 1.1, step=0.05)
    chunk_size = st.slider("청크 크기 (글자 수 기준)", 300, 1500, 800, step=50)
    translate_directives = st.checkbox("괄호 안 지시문 번역 ([whispering] -> [속삭임])", value=True)

# Sync chunks with original script
sync_chunks(chunk_size)

# Tabs
tab1, tab2, tab3, tab4 = st.tabs([
    "1. 대본 입력",
    "2. 페르소나 및 용어집 설정",
    "3. 번역 실행 및 실시간 보기",
    "4. 교정 및 결과 다운로드"
])

# Tab 1: Script Input
with tab1:
    st.header("대본 및 메타데이터 입력")
    
    # Meta description
    st.session_state.metadata_text = st.text_area(
        "ASMR 메타데이터 (소개글, 태그 등)", 
        value=st.session_state.metadata_text,
        placeholder="소개글이나 태그 등을 입력해 주세요.",
        height=120
    )
    
    # File Uploader
    uploaded_file = st.file_uploader("대본 파일 업로드 (.txt, .srt, .pdf)", type=["txt", "srt", "pdf"])
    
    # Image Uploader
    uploaded_images = st.file_uploader(
        "ASMR 소개 이미지 업로드 (선택사항)", 
        type=["png", "jpg", "jpeg"], 
        accept_multiple_files=True
    )
    
    # 소개 이미지 저장 및 세션 스테이트 반영
    if uploaded_images:
        project_dir = get_backup_dir(st.session_state.file_name)
        images_dir = os.path.join(project_dir, "images")
        # 이전 임시 이미지 삭제
        if os.path.exists(images_dir):
            for f in os.listdir(images_dir):
                try:
                    os.remove(os.path.join(images_dir, f))
                except Exception:
                    pass
        os.makedirs(images_dir, exist_ok=True)
        
        temp_image_paths = []
        for idx, img_file in enumerate(uploaded_images):
            img_path = os.path.join(images_dir, f"img_{idx}_{img_file.name}")
            with open(img_path, "wb") as f:
                f.write(img_file.read())
            temp_image_paths.append(img_path)
            
        st.session_state.temp_image_paths = temp_image_paths
        
        # 이미지 미리보기 레이아웃
        st.markdown("**업로드된 소개 이미지 미리보기**")
        max_cols_per_row = 4
        num_images = len(uploaded_images)
        for i in range(0, num_images, max_cols_per_row):
            row_images = uploaded_images[i:i + max_cols_per_row]
            cols = st.columns(len(row_images))
            for idx, img_file in enumerate(row_images):
                cols[idx].image(img_file, caption=img_file.name, use_container_width=True)
    elif st.session_state.temp_image_paths:
        # 이미 백업 폴더에 저장되어 있는 이미지 표시
        st.markdown("**불러온 백업 소개 이미지 미리보기**")
        max_cols_per_row = 4
        num_images = len(st.session_state.temp_image_paths)
        for i in range(0, num_images, max_cols_per_row):
            row_paths = st.session_state.temp_image_paths[i:i + max_cols_per_row]
            cols = st.columns(len(row_paths))
            for idx, img_path in enumerate(row_paths):
                cols[idx].image(img_path, caption=os.path.basename(img_path), use_container_width=True)
    
    # PDF 줄바꿈 보정용 체크박스
    clean_pdf_breaks = st.checkbox(
        "PDF 추출 시 줄바꿈 자동 보정", 
        value=True, 
        help="세로쓰기 등으로 인해 잘게 조각난 줄바꿈을 지능적으로 병합하여 번역 품질을 높입니다."
    )
    
    # Extract text from uploaded file
    if uploaded_file is not None:
        file_name = uploaded_file.name
        st.session_state.file_name = file_name
        
        if file_name.endswith(".pdf"):
            from core.translator import extract_text_from_pdf, clean_pdf_linebreaks
            extracted_text = extract_text_from_pdf(uploaded_file)
            if clean_pdf_breaks:
                extracted_text = clean_pdf_linebreaks(extracted_text)
            st.session_state.original_script = extracted_text
            st.success(f"PDF 파일에서 텍스트를 추출했습니다! ({len(extracted_text)} 자)")
        else:
            # txt or srt
            raw_data = uploaded_file.read()
            # Try decoding with utf-8, fallback to cp949 or unicode_escape
            try:
                extracted_text = raw_data.decode("utf-8")
            except UnicodeDecodeError:
                try:
                    extracted_text = raw_data.decode("cp949")
                except UnicodeDecodeError:
                    extracted_text = raw_data.decode("latin1")
            st.session_state.original_script = extracted_text
            st.success(f"자막/대본 파일 업로드 완료! ({len(extracted_text)} 자)")
            
    # Text input area
    st.session_state.original_script = st.text_area(
        "대본 원문 내용",
        value=st.session_state.original_script,
        placeholder="번역할 대본 본문을 직접 붙여넣거나 파일을 업로드해 주세요.",
        height=350
    )
    
    # 수동 줄바꿈 정제 실행 버튼
    if st.button("수동 줄바꿈 정제 실행", help="현재 본문 내의 과도한 줄바꿈을 문장 단위로 병합합니다. (세로쓰기 시나리오를 직접 붙여넣었을 때 유용합니다)"):
        if st.session_state.original_script.strip():
            from core.translator import clean_pdf_linebreaks
            cleaned = clean_pdf_linebreaks(st.session_state.original_script)
            st.session_state.original_script = cleaned
            st.success("대본 본문의 줄바꿈 정제를 완료했습니다!")
            st.rerun()

# Tab 2: Persona and Glossary Setup
with tab2:
    st.header("페르소나 및 용어집 설정")
    
    col1, col2 = st.columns(2)
    
    with col1:
        st.subheader("캐릭터 페르소나 설정")
        st.caption("대본 번역 시 적용할 캐릭터의 어투와 성격 규칙입니다.")
        
        # Analyze button
        if st.button("대본 분석 및 페르소나 자동 생성", use_container_width=True):
            if not st.session_state.model_loaded:
                st.error("먼저 사이드바에서 모델을 로드해주세요!")
            elif not st.session_state.original_script and not st.session_state.metadata_text:
                st.error("페르소나 분석을 위해 대본 원문이나 메타데이터를 입력해 주세요.")
            else:
                from core.analyzer import analyze_persona
                # Use first 1000 characters of script for preview
                script_preview = st.session_state.original_script[:1000]
                with st.spinner("AI가 대본과 메타데이터를 분석하여 페르소나를 도출 중입니다..."):
                    try:
                        # 단일 스레드풀에서 분석 실행 (GPU 스트림 스레드 일치 + 소개 이미지 경로 전달)
                        future = EXECUTOR.submit(
                            analyze_persona,
                            st.session_state.model,
                            st.session_state.processor,
                            st.session_state.metadata_text,
                            script_preview,
                            st.session_state.temp_image_paths
                        )
                        extracted_persona = future.result()
                        # 페르소나 매핑
                        st.session_state.persona = {
                            "tone": extracted_persona.get("tone", ""),
                            "relationship": extracted_persona.get("relationship", ""),
                            "key_rules": extracted_persona.get("key_rules", [])
                        }
                        
                        # 요약 정보 매핑
                        if "summary" in extracted_persona:
                            st.session_state.script_summary = {
                                "speaker_name": extracted_persona["summary"].get("speaker_name", "미분석"),
                                "listener_role": extracted_persona["summary"].get("listener_role", "미분석"),
                                "situation": extracted_persona["summary"].get("situation", "미분석"),
                                "story": extracted_persona["summary"].get("story", "미분석")
                            }
                        
                        # 용어집 추출 및 자동 입력
                        if "glossary" in extracted_persona:
                            new_glossary = []
                            for item in extracted_persona["glossary"]:
                                src = item.get("source") or item.get("원어")
                                tgt = item.get("target") or item.get("번역어")
                                if src and tgt:
                                    new_glossary.append({"원어 (Source)": src, "번역어 (Target)": tgt})
                            if new_glossary:
                                st.session_state.glossary_data = new_glossary
                                
                        st.success("페르소나 및 용어집 자동 추출 완료!")
                        st.rerun()
                    except Exception as e:
                        import traceback
                        st.error(f"분석 중 오류 발생: {e}")
                        st.code(traceback.format_exc(), language="python")
                        
        # Editable inputs
        st.session_state.persona["tone"] = st.text_input(
            "어조 및 말투", 
            value=st.session_state.persona.get("tone", "")
        )
        st.session_state.persona["relationship"] = st.text_input(
            "화자-청자 관계", 
            value=st.session_state.persona.get("relationship", "")
        )
        
        # Key rules text area
        key_rules_str = st.text_area(
            "어조 규칙 (줄 바꿈으로 구분)",
            value="\n".join(st.session_state.persona.get("key_rules", [])),
            height=150
        )
        st.session_state.persona["key_rules"] = [r.strip() for r in key_rules_str.split("\n") if r.strip()]

    with col2:
        st.subheader("용어집 (Word Mapping)")
        st.caption("특정 고유 명사나 ASMR용 단어가 지정한 한글 단어로 고정 번역되도록 정의합니다.")
        
        # Data Editor for interactive glossary editing
        glossary_df = pd.DataFrame(st.session_state.glossary_data)
        
        # Streamlit interactive data editor
        edited_df = st.data_editor(
            glossary_df, 
            num_rows="dynamic",
            use_container_width=True,
            column_config={
                "원어 (Source)": st.column_config.TextColumn("원어 (영문/일문 등)", help="원본 텍스트 내 매칭 단어", required=True),
                "번역어 (Target)": st.column_config.TextColumn("고정 번역어 (한글)", help="출력될 한글 단어", required=True)
            }
        )
        
        # Convert edited dataframe back to list of dicts
        st.session_state.glossary_data = edited_df.to_dict(orient="records")
        
    # 2번 탭 최하단에 분석된 상황 및 줄거리 요약 표시
    st.divider()
    st.subheader("대본 상황 및 스토리 요약")
    st.caption("대본 분석을 통해 자동으로 도출된 주인공 설정, 배경 상황 및 대략적인 스토리 흐름입니다.")
    
    sum_data = st.session_state.script_summary
    
    col_sum1, col_sum2 = st.columns(2)
    with col_sum1:
        st.info(f"**화자 (주인공 이름/칭호)**\n\n{sum_data.get('speaker_name', '미분석')}")
    with col_sum2:
        st.success(f"**청자 (상대방 역할/칭호)**\n\n{sum_data.get('listener_role', '미분석')}")
        
    st.markdown("##### 배경 상황 및 설정 요약")
    st.write(sum_data.get("situation", "대본 분석 전입니다."))
    
    st.markdown("##### 전체 줄거리 흐름")
    st.write(sum_data.get("story", "대본 분석 전입니다."))

# Tab 3: Translate and Stream View
with tab3:
    st.header("대본 번역 실행 및 실시간 진행 상태")
    
    total_chunks = len(st.session_state.chunks)
    translated_count = sum(1 for c in st.session_state.translated_chunks if c.strip())
    
    if total_chunks > 0:
        st.info(f"전체 {total_chunks}개 청크 중 {translated_count}개 청크의 번역이 완료(임시저장)되었습니다.")
        
    col_act1, col_act2 = st.columns(2)
    with col_act1:
        start_btn = st.button("번역 실행 / 이어서 번역", type="primary", use_container_width=True)
    with col_act2:
        reset_btn = st.button("번역 진행 상태 초기화", use_container_width=True)
        
    if reset_btn:
        if total_chunks > 0:
            st.session_state.translated_chunks = [""] * total_chunks
            st.session_state.translated_script = ""
            backup_path = get_backup_path(st.session_state.file_name)
            if os.path.exists(backup_path):
                try:
                    os.remove(backup_path)
                except Exception:
                    pass
            st.success("진행 상태가 초기화되었습니다.")
            st.rerun()

    if start_btn:
        if not st.session_state.model_loaded:
            st.error("먼저 사이드바에서 모델을 로드해주세요!")
        elif not st.session_state.original_script.strip():
            st.error("번역할 대본이 없습니다. '1. 대본 입력' 탭에서 대본을 추가해 주세요.")
        else:
            from core.translator import translate_script, chunk_text, chunk_srt, clean_markdown
            from streamlit.runtime.scriptrunner import add_script_run_ctx, get_script_run_ctx
            import threading
            
            ctx = get_script_run_ctx()
            
            def translate_with_context(ctx, *args, **kwargs):
                add_script_run_ctx(threading.current_thread(), ctx)
                return translate_script(*args, **kwargs)
            
            is_srt = st.session_state.file_name.endswith(".srt")
            
            # Prepare glossary dict
            glossary_dict = {}
            for item in st.session_state.glossary_data:
                src = item.get("원어 (Source)", "")
                tgt = item.get("번역어 (Target)", "")
                if src and tgt:
                    glossary_dict[str(src).strip()] = str(tgt).strip()
            
            # Setup layout for progress
            progress_bar = st.progress(0.0)
            progress_status = st.empty()
            
            col_orig, col_trans = st.columns(2)
            with col_orig:
                st.markdown("#### 현재 번역 진행 중인 원문 청크")
                orig_box = st.empty()
            with col_trans:
                st.markdown("#### 실시간 로컬 LLM 번역 스트리밍")
                trans_box = st.empty()
                
            st.markdown("#### 지금까지 번역된 전체 텍스트")
            full_translated_box = st.empty()
            
            chunks = st.session_state.chunks
            
            # Fill existing translation box
            initial_full_text = "\n\n".join([c for c in st.session_state.translated_chunks if c])
            full_translated_box.markdown(
                f'<div style="border: 1px solid #31333f; padding: 20px; border-radius: 8px; background-color: #0e1117; color: #f0f2f6; white-space: pre-wrap; font-size: 14px; height: 400px; overflow-y: auto;">{colorize_directives(initial_full_text)}</div>',
                unsafe_allow_html=True
            )
            
            def update_progress(token_text, chunk_idx, total_chunks, current_chunk_translation):
                # Update progress bar
                progress_bar.progress((chunk_idx + 1) / total_chunks)
                progress_status.markdown(f"**진행 상태**: 청크 {chunk_idx + 1} / {total_chunks} 번역 중...")
                
                # Show current chunk original
                orig_box.info(chunks[chunk_idx])
                
                # Show streaming translation
                colorized_chunk = colorize_directives(current_chunk_translation)
                trans_box.markdown(
                    f'<div style="border: 1px solid #ff4b4b; padding: 15px; border-radius: 8px; background-color: #0e1117; color: #f0f2f6; white-space: pre-wrap; font-size: 15px;">{colorized_chunk}</div>',
                    unsafe_allow_html=True
                )
                
                # Keep track of current translation and auto-save
                st.session_state.translated_chunks[chunk_idx] = clean_markdown(current_chunk_translation)
                save_progress_backup()
                
                # Join all translated chunks and show colorized full text
                full_text = "\n\n".join([c for c in st.session_state.translated_chunks if c])
                colorized_full = colorize_directives(full_text)
                full_translated_box.markdown(
                    f'<div style="border: 1px solid #31333f; padding: 20px; border-radius: 8px; background-color: #0e1117; color: #f0f2f6; white-space: pre-wrap; font-size: 14px; height: 400px; overflow-y: auto;">{colorized_full}</div>',
                    unsafe_allow_html=True
                )
                
            try:
                # 단일 스레드풀에서 번역 실행 (GPU 스트림 스레드 일치 + existing_translations 전달)
                future = EXECUTOR.submit(
                    translate_with_context,
                    ctx,
                    st.session_state.model,
                    st.session_state.processor,
                    st.session_state.original_script,
                    st.session_state.persona,
                    glossary_dict,
                    is_srt=is_srt,
                    translate_directives=translate_directives,
                    chunk_size=chunk_size,
                    temp=temperature,
                    repetition_penalty=repetition_penalty,
                    existing_translations=st.session_state.translated_chunks,
                    progress_callback=update_progress
                )
                final_translation = future.result()
                
                st.session_state.translated_script = final_translation
                progress_status.markdown("**번역 완료! 번역 결과를 저장했습니다.**")
                st.balloons()
            except Exception as e:
                import traceback
                st.error(f"번역 중 오류 발생: {e}")
                st.code(traceback.format_exc(), language="python")

    # Add expander for chunk-by-chunk management
    if total_chunks > 0:
        st.divider()
        with st.expander("개별 청크 상세 관리 및 부분 재번역", expanded=False):
            st.caption("각 번역 조각의 원문과 번역을 대조/수정하고, 마음에 들지 않는 조각만 개별 재번역할 수 있습니다.")
            is_srt = st.session_state.file_name.endswith(".srt")
            
            # Prepare glossary dict for re-translation
            glossary_dict = {}
            for item in st.session_state.glossary_data:
                src = item.get("원어 (Source)", "")
                tgt = item.get("번역어 (Target)", "")
                if src and tgt:
                    glossary_dict[str(src).strip()] = str(tgt).strip()
            
            for idx in range(total_chunks):
                with st.container():
                    col_c1, col_c2, col_c3 = st.columns([5, 5, 2])
                    with col_c1:
                        st.text_area(f"청크 {idx+1} 원문", st.session_state.chunks[idx], height=120, key=f"chunk_orig_{idx}", disabled=True)
                    with col_c2:
                        new_trans = st.text_area(f"청크 {idx+1} 번역", st.session_state.translated_chunks[idx], height=120, key=f"chunk_trans_{idx}")
                        if new_trans != st.session_state.translated_chunks[idx]:
                            st.session_state.translated_chunks[idx] = new_trans
                            save_progress_backup()
                            # Update full translation script text
                            if is_srt:
                                st.session_state.translated_script = "\n\n".join([c for c in st.session_state.translated_chunks if c])
                            else:
                                st.session_state.translated_script = "\n".join([c for c in st.session_state.translated_chunks if c])
                    with col_c3:
                        st.markdown("<div style='height: 25px;'></div>", unsafe_allow_html=True)
                        has_translation = bool(st.session_state.translated_chunks[idx].strip())
                        btn_label = "부분 재번역" if has_translation else "부분 번역"
                        
                        # Translate / Re-translate button
                        if st.button(btn_label, key=f"retrans_btn_{idx}", use_container_width=True):
                            if not st.session_state.model_loaded:
                                st.error("모델 로드 필요!")
                            else:
                                with st.spinner(f"청크 {idx+1} {btn_label} 중..."):
                                    try:
                                        prev_orig = st.session_state.chunks[idx-1] if idx > 0 else ""
                                        prev_trans = st.session_state.translated_chunks[idx-1] if idx > 0 else ""
                                        
                                        from core.translator import build_translation_prompt, build_retranslation_prompt, clean_markdown
                                        from mlx_vlm import generate as mlx_generate
                                        from mlx_vlm.prompt_utils import apply_chat_template
                                        
                                        # 번역 내용이 있으면 재번역 프롬프트, 없으면 일반 번역 프롬프트 사용
                                        if has_translation:
                                            prompt = build_retranslation_prompt(
                                                current_chunk=st.session_state.chunks[idx],
                                                existing_translation=st.session_state.translated_chunks[idx],
                                                prev_original=prev_orig,
                                                prev_translated=prev_trans,
                                                persona=st.session_state.persona,
                                                glossary=glossary_dict,
                                                is_srt=is_srt,
                                                translate_directives=translate_directives
                                            )
                                        else:
                                            prompt = build_translation_prompt(
                                                current_chunk=st.session_state.chunks[idx],
                                                prev_original=prev_orig,
                                                prev_translated=prev_trans,
                                                persona=st.session_state.persona,
                                                glossary=glossary_dict,
                                                is_srt=is_srt,
                                                translate_directives=translate_directives
                                            )
                                        
                                        # 백그라운드 스레드에서 모델 및 프로세서에 안전하게 직접 접근하도록 인자로 전달
                                        def retranslate_single_chunk_task(model, processor, prompt):
                                            messages = [{"role": "user", "content": prompt}]
                                            formatted_prompt = apply_chat_template(
                                                processor,
                                                model.config,
                                                messages,
                                                num_images=0,
                                                num_audios=0
                                            )
                                            res = mlx_generate(
                                                model,
                                                processor,
                                                prompt=formatted_prompt,
                                                temp=temperature,
                                                max_tokens=1500,
                                                kv_bits=3.5,
                                                kv_quant_scheme="turboquant",
                                                repetition_penalty=repetition_penalty,
                                                repetition_context_size=100
                                            )
                                            return clean_markdown(res.text)
                                            
                                        future = EXECUTOR.submit(
                                            retranslate_single_chunk_task,
                                            st.session_state.model,
                                            st.session_state.processor,
                                            prompt
                                        )
                                        new_translated_text = future.result()
                                        
                                        st.session_state.translated_chunks[idx] = new_translated_text
                                        save_progress_backup()
                                        
                                        # Update full translation script text
                                        if is_srt:
                                            st.session_state.translated_script = "\n\n".join([c for c in st.session_state.translated_chunks if c])
                                        else:
                                            st.session_state.translated_script = "\n".join([c for c in st.session_state.translated_chunks if c])
                                            
                                        st.success(f"청크 {idx+1} {btn_label} 성공!")
                                        st.rerun()
                                    except Exception as ex:
                                        st.error(f"{btn_label} 중 오류: {ex}")
                                        
                        # Clear translation button (only if translation exists)
                        if has_translation:
                            if st.button("번역 지우기", key=f"clear_btn_{idx}", use_container_width=True):
                                st.session_state.translated_chunks[idx] = ""
                                save_progress_backup()
                                if is_srt:
                                    st.session_state.translated_script = "\n\n".join([c for c in st.session_state.translated_chunks if c])
                                else:
                                    st.session_state.translated_script = "\n".join([c for c in st.session_state.translated_chunks if c])
                                st.rerun()
                st.divider()

# Tab 4: Refine & Download
with tab4:
    st.header("최종 결과 검토 및 교정")
    
    st.session_state.translated_script = st.text_area(
        "최종 번역 결과물",
        value=st.session_state.translated_script,
        height=350
    )
    
    col_ref, col_down = st.columns(2)
    
    with col_ref:
        st.subheader("말투 및 포맷 자동 교정 (Refiner)")
        st.caption("문장의 어조 일관성을 잡고 괄호 매칭 에러 등을 보정합니다.")
        if st.button("후처리 교정 실행", use_container_width=True):
            if not st.session_state.model_loaded:
                st.error("먼저 사이드바에서 모델을 로드해주세요!")
            elif not st.session_state.translated_script.strip():
                st.error("교정할 번역 결과물이 존재하지 않습니다.")
            else:
                from core.refiner import refine_translation
                with st.spinner("번역 결과의 말투와 지시문 구조를 교정하고 있습니다..."):
                    try:
                        # 단일 스레드풀에서 교정 실행 (GPU 스트림 스레드 일치)
                        future = EXECUTOR.submit(
                            refine_translation,
                            st.session_state.model,
                            st.session_state.processor,
                            st.session_state.translated_script,
                            st.session_state.persona
                        )
                        refined_text = future.result()
                        st.session_state.translated_script = refined_text
                        st.success("후처리 교정 완료!")
                        st.rerun()
                    except Exception as e:
                        import traceback
                        st.error(f"교정 중 오류 발생: {e}")
                        st.code(traceback.format_exc(), language="python")
                        
    with col_down:
        st.subheader("파일 다운로드")
        st.caption("번역 및 교정이 완료된 파일을 로컬 컴퓨터로 다운로드합니다.")
        
        # Suggest download file name
        base_name, ext = os.path.splitext(st.session_state.file_name)
        download_name = f"{base_name}_translated{ext}"
        
        st.download_button(
            label="번역 대본 파일 다운로드",
            data=st.session_state.translated_script,
            file_name=download_name,
            mime="text/plain" if not ext == ".srt" else "text/srt",
            use_container_width=True
        )
