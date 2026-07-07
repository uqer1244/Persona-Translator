import streamlit as st
import os
import pandas as pd

from core.utils import (
    EXECUTOR,
    LiveStatus,
    colorize_directives,
    get_backup_dir,
    get_backup_path,
    save_progress_backup,
    sync_chunks,
    load_model_cached,
    extract_script_structure,
    unload_model
)
from core.progress_store import save_progress
from core.progress_store import get_image_note_path, load_image_note


def clear_chunk_callback(idx):
    if "translated_chunks" in st.session_state and idx < len(st.session_state.translated_chunks):
        st.session_state.translated_chunks[idx] = ""
        st.session_state[f"chunk_trans_{idx}"] = ""
        save_progress(
            st.session_state.file_name,
            st.session_state.chunks,
            st.session_state.translated_chunks,
        )
        is_srt = st.session_state.file_name.endswith(".srt")
        if is_srt:
            st.session_state.translated_script = "\n\n".join([c for c in st.session_state.translated_chunks if c])
        else:
            st.session_state.translated_script = "\n".join([c for c in st.session_state.translated_chunks if c])


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
        "situation": "",
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
if "image_generation_prompt" not in st.session_state:
    st.session_state.image_generation_prompt = ""
if "chunks" not in st.session_state:
    st.session_state.chunks = []
if "translated_chunks" not in st.session_state:
    st.session_state.translated_chunks = []
if "batch_future" not in st.session_state:
    st.session_state.batch_future = None
if "batch_cancel_token" not in st.session_state:
    st.session_state.batch_cancel_token = {"cancel": False}
if "single_futures" not in st.session_state:
    st.session_state.single_futures = {}
if "single_cancel_tokens" not in st.session_state:
    st.session_state.single_cancel_tokens = {}


# LIVE_STATUS session state initialization
if "LIVE_STATUS" not in st.session_state:
    st.session_state.LIVE_STATUS = LiveStatus()

LIVE_STATUS = st.session_state.LIVE_STATUS

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
    local_models.sort(key=lambda path: ("8bit" in path.lower(), "4bit" not in path.lower(), path.lower()))
                
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
    is_high_memory_model = "8bit" in model_path.lower()
    allow_high_memory_model = False
    if is_high_memory_model:
        st.warning("8bit 12B 모델은 메모리 부족으로 Python 프로세스가 종료될 수 있습니다. 가능하면 4bit 모델을 먼저 사용하세요.")
        allow_high_memory_model = st.checkbox("위험을 이해하고 8bit 모델 로딩 허용", value=False)
    
    # Model load button
    if not st.session_state.model_loaded:
        st.markdown('<div class="status-box status-warn">모델 로드 필요</div>', unsafe_allow_html=True)
        if st.button("로컬 모델 메모리에 로딩", use_container_width=True):
            if is_high_memory_model and not allow_high_memory_model:
                st.error("메모리 보호를 위해 8bit 모델 로딩을 막았습니다. 4bit 모델을 선택하거나 허용 체크박스를 켜 주세요.")
            elif not os.path.exists(model_path) and not "/" in model_path:
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
        if st.button("모델 메모리 언로드", use_container_width=True):
            unload_model()
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
    uploaded_files = st.file_uploader("대본 파일 업로드 (.txt, .srt, .pdf)", type=["txt", "srt", "pdf"], accept_multiple_files=True)
    
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
        os.makedirs(images_dir, exist_ok=True)
        
        temp_image_paths = []
        for idx, img_file in enumerate(uploaded_images):
            raw_image = img_file.read()
            import hashlib

            image_hash = hashlib.sha256(raw_image).hexdigest()[:12]
            image_stem = os.path.splitext(img_file.name)[0]
            safe_stem = "".join(ch if ch.isalnum() or ch in ("-", "_") else "_" for ch in image_stem)
            img_path = os.path.join(images_dir, f"img_{idx}_{safe_stem}_{image_hash}.jpg")
            try:
                from PIL import Image
                import io

                image = Image.open(io.BytesIO(raw_image)).convert("RGB")
                image.thumbnail((768, 768))
                image.save(img_path, format="JPEG", quality=82, optimize=True)
            except Exception:
                with open(img_path, "wb") as f:
                    f.write(raw_image)
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
    if uploaded_files:
        if st.button("업로드된 대본 파일 파싱 및 불러오기", type="primary", use_container_width=True):
            import re
            sorted_files = sorted(uploaded_files, key=lambda f: f.name)
            combined_text = []
            srt_count = sum(1 for f in sorted_files if f.name.endswith('.srt'))
            is_srt_mode = srt_count == len(sorted_files)

            for idx, file in enumerate(sorted_files):
                file_name = file.name
                if file_name.endswith('.pdf'):
                    from core.translator import extract_text_from_pdf, clean_pdf_linebreaks
                    extracted_text = extract_text_from_pdf(file)
                    if clean_pdf_breaks:
                        extracted_text = clean_pdf_linebreaks(extracted_text)
                else:
                    raw_data = file.read()
                    try:
                        extracted_text = raw_data.decode('utf-8')
                    except UnicodeDecodeError:
                        try:
                            extracted_text = raw_data.decode('cp949')
                        except UnicodeDecodeError:
                            extracted_text = raw_data.decode('latin1')

                # 여러 대본을 합칠 때 경계 마크 추가
                if len(sorted_files) > 1:
                    if is_srt_mode:
                        combined_text.append(extracted_text.strip())
                    else:
                        track_name = f'Track {idx + 1}'
                        num_match = re.search(r'\d+', file_name)
                        if num_match:
                            track_name = f'Track {num_match.group(0)}'
                        combined_text.append(f'[{track_name} ({file_name})]\n{extracted_text.strip()}')
                else:
                    combined_text.append(extracted_text.strip())

            sep = '\n\n' if is_srt_mode else '\n\n\n'
            st.session_state.original_script = sep.join(combined_text)

            if len(sorted_files) == 1:
                st.session_state.file_name = sorted_files[0].name
            else:
                first_name, _ = os.path.splitext(sorted_files[0].name)
                st.session_state.file_name = f'{first_name}_외_{len(sorted_files)-1}개' + ('.srt' if is_srt_mode else '.txt')

            st.success(f'총 {len(sorted_files)}개 대본 파일에서 텍스트를 추출하고 병합했습니다! ({len(st.session_state.original_script)} 자)')
            st.rerun()

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
        
        # Persona analyze button
        if st.button("페르소나 및 용어집 자동 생성", use_container_width=True):
            if not st.session_state.model_loaded:
                st.error("먼저 사이드바에서 모델을 로드해주세요!")
            elif not st.session_state.original_script and not st.session_state.metadata_text:
                st.error("페르소나 분석을 위해 대본 원문이나 메타데이터를 입력해 주세요.")
            else:
                from core.analyzer import analyze_persona
                script_preview = extract_script_structure(
                    st.session_state.original_script,
                    file_name=st.session_state.file_name,
                    max_total_chars=3000
                )
                with st.spinner("AI가 대본과 메타데이터를 분석하여 페르소나를 도출 중입니다..."):
                    try:
                        future = EXECUTOR.submit(
                            analyze_persona,
                            st.session_state.model,
                            st.session_state.processor,
                            st.session_state.metadata_text,
                            script_preview,
                            st.session_state.temp_image_paths
                        )
                        extracted_persona = future.result()
                        st.session_state.persona = {
                            "tone": extracted_persona.get("tone", ""),
                            "relationship": extracted_persona.get("relationship", ""),
                            "situation": extracted_persona.get("situation", ""),
                            "key_rules": extracted_persona.get("key_rules", [])
                        }

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
        st.session_state.persona["situation"] = st.text_area(
            "배경 상황 및 스토리 맥락 요약", 
            value=st.session_state.persona.get("situation", ""),
            height=60
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
    st.subheader("소개 이미지 분석 결과")
    st.caption("업로드한 이미지를 VLM이 어떻게 이해했는지 확인합니다. 분석 결과는 temp_backups의 이미지 파일 옆에 저장됩니다.")

    if st.session_state.temp_image_paths:
        for idx, img_path in enumerate(st.session_state.temp_image_paths, start=1):
            note = load_image_note(img_path)
            note_path = get_image_note_path(img_path)
            with st.expander(f"이미지 {idx}: {os.path.basename(img_path)}", expanded=False):
                col_img, col_note = st.columns([1, 2])
                with col_img:
                    st.image(img_path, use_container_width=True)
                with col_note:
                    st.caption(f"저장 위치: {note_path}")
                    if note:
                        st.markdown(note)
                    else:
                        st.info("아직 이미지 분석 결과가 없습니다. 페르소나 생성 버튼을 누르면 자동으로 생성됩니다.")
    else:
        st.info("업로드되었거나 백업에서 불러온 소개 이미지가 없습니다.")



    # 8. 저장된 다른 페르소나 설정 불러오기 및 현재 설정 자동저장
    st.divider()
    st.subheader("💾 페르소나 설정 저장 및 라이브러리")
    st.caption("이전 프로젝트에서 도출했던 페르소나 설정을 불러와 현재 대본 번역에 재사용할 수 있습니다.")
    
    from core.progress_store import list_saved_personas, load_persona_by_project_name, save_persona_backup
    
    saved_projects = list_saved_personas()
    col_lib1, col_lib2 = st.columns([3, 1])
    
    with col_lib1:
        selected_proj = st.selectbox(
            "저장된 페르소나 라이브러리 선택",
            options=["선택 안 함"] + saved_projects,
            index=0,
            help="기존에 작업했던 프로젝트 폴더에서 페르소나 정보를 가져옵니다."
        )
    with col_lib2:
        st.markdown("<div style='height: 28px;'></div>", unsafe_allow_html=True)
        if st.button("설정 불러오기", use_container_width=True, disabled=(selected_proj == "선택 안 함")):
            p_data = load_persona_by_project_name(selected_proj)
            if p_data:
                if "persona" in p_data and p_data["persona"]:
                    st.session_state.persona = p_data["persona"]
                if "glossary_data" in p_data and p_data["glossary_data"]:
                    st.session_state.glossary_data = p_data["glossary_data"]
                st.success(f"'{selected_proj}' 프로젝트의 페르소나 설정을 성공적으로 적용했습니다!")
                st.rerun()
            else:
                st.error("설정을 불러오는데 실패했습니다.")

    # 실시간 데이터 자동 저장 (Autosave)
    if st.session_state.original_script.strip() and st.session_state.file_name:
        save_persona_backup(
            st.session_state.file_name,
            st.session_state.persona,
            st.session_state.glossary_data
        )

# Tab 3: Translate and Stream View
with tab3:
    st.header("대본 번역 실행 및 실시간 진행 상태")
    
    total_chunks = len(st.session_state.chunks)
    translated_count = sum(1 for c in st.session_state.translated_chunks if c.strip())
    
    # 1. 스레드 동기화 (백그라운드에서 완료된 번역이 있다면 메인 세션에 커밋)
    new_saved = False
    for idx, trans_text in list(LIVE_STATUS.completed_translations.items()):
        if idx < len(st.session_state.translated_chunks):
            st.session_state.translated_chunks[idx] = trans_text
            st.session_state[f"chunk_trans_{idx}"] = trans_text
            new_saved = True
            if idx in LIVE_STATUS.completed_translations:
                del LIVE_STATUS.completed_translations[idx]
    if new_saved:
        save_progress_backup()
        is_srt = st.session_state.file_name.endswith(".srt")
        if is_srt:
            st.session_state.translated_script = "\n\n".join([c for c in st.session_state.translated_chunks if c])
        else:
            st.session_state.translated_script = "\n".join([c for c in st.session_state.translated_chunks if c])
        
    new_single_saved = False
    for idx, trans_text in list(LIVE_STATUS.single_completed_translations.items()):
        if idx < len(st.session_state.translated_chunks):
            st.session_state.translated_chunks[idx] = trans_text
            st.session_state[f"chunk_trans_{idx}"] = trans_text
            new_single_saved = True
            # Clean up single task records once saved
            if idx in st.session_state.single_futures:
                st.session_state.single_futures[idx] = None
            if idx in LIVE_STATUS.single_streaming_text:
                del LIVE_STATUS.single_streaming_text[idx]
            if idx in LIVE_STATUS.single_completed_translations:
                del LIVE_STATUS.single_completed_translations[idx]
    if new_single_saved:
        save_progress_backup()
        is_srt = st.session_state.file_name.endswith(".srt")
        if is_srt:
            st.session_state.translated_script = "\n\n".join([c for c in st.session_state.translated_chunks if c])
        else:
            st.session_state.translated_script = "\n".join([c for c in st.session_state.translated_chunks if c])

    # 2. 번역 실행 상태 점검 및 에러 처리
    if st.session_state.batch_future is not None and st.session_state.batch_future.done():
        try:
            exc = st.session_state.batch_future.exception()
            if exc:
                st.error(f"일괄 번역 중 오류가 발생했습니다: {exc}")
        except Exception:
            pass
        st.session_state.batch_future = None
        LIVE_STATUS.current_chunk_idx = -1
        LIVE_STATUS.current_streaming_text = ""

    for idx, f in list(st.session_state.single_futures.items()):
        if f is not None and f.done():
            try:
                exc = f.exception()
                if exc:
                    st.error(f"청크 {idx+1} 번역 중 오류가 발생했습니다: {exc}")
            except Exception:
                pass
            st.session_state.single_futures[idx] = None
            if idx in LIVE_STATUS.single_streaming_text:
                del LIVE_STATUS.single_streaming_text[idx]

    is_batch_running = st.session_state.batch_future is not None and not st.session_state.batch_future.done()
    is_single_running = any(f is not None and not f.done() for f in st.session_state.single_futures.values())

    if total_chunks > 0:
        st.info(f"전체 {total_chunks}개 청크 중 {translated_count}개 청크의 번역이 완료(임시저장)되었습니다.")

    # 3. 일괄 번역 진행바 및 중지 컨트롤
    if is_batch_running:
        curr_idx = LIVE_STATUS.current_chunk_idx
        # Ensure curr_idx bounds
        if curr_idx < 0:
            curr_idx = 0
        progress_val = min(1.0, max(0.0, (curr_idx) / total_chunks))
        
        st.progress(progress_val)
        st.subheader(f"⏳ 전체 번역 진행 중 (청크 {curr_idx + 1} / {total_chunks})")
        
        col_abort1, col_abort2 = st.columns([3, 1])
        with col_abort1:
            st.warning("일괄 번역이 실행 중입니다. 중지 버튼을 누르면 현재 진행 중인 구역의 작업은 저장되지 않고 멈춥니다.")
        with col_abort2:
            if st.button("일괄 번역 중지", key="stop_batch_btn", type="primary", use_container_width=True):
                st.session_state.batch_cancel_token["cancel"] = True
                st.session_state.batch_future = None
                LIVE_STATUS.current_chunk_idx = -1
                LIVE_STATUS.current_streaming_text = ""
                st.warning("중지하는 중...")
                st.rerun()

        col_orig_live, col_trans_live = st.columns(2)
        with col_orig_live:
            st.markdown("##### 현재 번역 중인 원문 청크")
            curr_orig_text = st.session_state.chunks[curr_idx] if curr_idx < len(st.session_state.chunks) else ""
            st.info(curr_orig_text)
        with col_trans_live:
            st.markdown("##### 실시간 로컬 LLM 스트리밍")
            colorized_stream = colorize_directives(LIVE_STATUS.current_streaming_text)
            st.markdown(
                f'<div style="border: 1px solid #ff4b4b; padding: 15px; border-radius: 8px; background-color: #0e1117; color: #f0f2f6; white-space: pre-wrap; font-size: 15px;">{colorized_stream}</div>',
                unsafe_allow_html=True
            )
            
    else:
        # 번역 미실행 시 메인 컨트롤 노출
        col_act1, col_act2 = st.columns(2)
        with col_act1:
            start_btn = st.button("번역 실행 / 이어서 번역", type="primary", use_container_width=True, disabled=is_single_running)
        with col_act2:
            reset_btn = st.button("번역 진행 상태 초기화", use_container_width=True, disabled=is_single_running)
            
        if reset_btn:
            if total_chunks > 0:
                st.session_state.translated_chunks = [""] * total_chunks
                st.session_state.translated_script = ""
                for idx in range(total_chunks):
                    st.session_state[f"chunk_trans_{idx}"] = ""
                backup_path = get_backup_path(st.session_state.file_name)
                if os.path.exists(backup_path):
                    try:
                        import shutil
                        shutil.rmtree(os.path.dirname(backup_path))
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
                from core.translator import translate_script
                from streamlit.runtime.scriptrunner import add_script_run_ctx, get_script_run_ctx
                import threading
                
                ctx = get_script_run_ctx()
                
                def translate_with_context(ctx, *args, **kwargs):
                    add_script_run_ctx(threading.current_thread(), ctx)
                    return translate_script(*args, **kwargs)
                
                is_srt = st.session_state.file_name.endswith(".srt")
                
                glossary_dict = {}
                for item in st.session_state.glossary_data:
                    src = item.get("원어 (Source)", "")
                    tgt = item.get("번역어 (Target)", "")
                    if src and tgt:
                        glossary_dict[str(src).strip()] = str(tgt).strip()
                
                st.session_state.batch_cancel_token = {"cancel": False}
                LIVE_STATUS.current_chunk_idx = -1
                LIVE_STATUS.current_streaming_text = ""
                LIVE_STATUS.completed_translations = {}
                
                file_name_captured = st.session_state.file_name
                original_chunks_captured = list(st.session_state.chunks)
                translated_chunks_snapshot = list(st.session_state.translated_chunks)
                
                def update_progress(token_text, chunk_idx, total_chunks, current_chunk_translation, is_finished):
                    LIVE_STATUS.current_chunk_idx = chunk_idx
                    LIVE_STATUS.current_streaming_text = current_chunk_translation
                    if is_finished:
                        from core.translator import clean_markdown
                        clean_txt = clean_markdown(current_chunk_translation)
                        LIVE_STATUS.completed_translations[chunk_idx] = clean_txt
                        try:
                            translated_chunks_snapshot[chunk_idx] = clean_txt
                            save_progress(
                                file_name_captured,
                                original_chunks_captured,
                                translated_chunks_snapshot,
                            )
                        except Exception:
                            pass

                    # Real-time Streamlit UI rerun trigger
                    import time
                    now = time.time()
                    if not hasattr(LIVE_STATUS, '_last_rerun_time'):
                        LIVE_STATUS._last_rerun_time = 0
                    if now - LIVE_STATUS._last_rerun_time > 0.1 or is_finished:
                        LIVE_STATUS._last_rerun_time = now
                        try:
                            from streamlit.runtime import get_instance
                            runtime = get_instance()
                            session_info = runtime._session_mgr.get_active_session_info(ctx.session_id)
                            if session_info:
                                session_info.session.request_rerun(None)
                        except Exception:
                            pass

                st.session_state.batch_future = EXECUTOR.submit(
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
                    cancel_token=st.session_state.batch_cancel_token,
                    progress_callback=update_progress
                )
                st.rerun()

    # 4. 실시간 전체 텍스트 렌더링
    st.markdown("#### 지금까지 번역된 전체 텍스트")
    temp_chunks = list(st.session_state.translated_chunks)
    if is_batch_running and 0 <= LIVE_STATUS.current_chunk_idx < len(temp_chunks):
        from core.translator import clean_markdown
        temp_chunks[LIVE_STATUS.current_chunk_idx] = clean_markdown(LIVE_STATUS.current_streaming_text)
    
    full_text = "\n\n".join([c for c in temp_chunks if c])
    st.markdown(
        f'<div style="border: 1px solid #31333f; padding: 20px; border-radius: 8px; background-color: #0e1117; color: #f0f2f6; white-space: pre-wrap; font-size: 14px; height: 300px; overflow-y: auto;">{colorize_directives(full_text)}</div>',
        unsafe_allow_html=True
    )

    # 5. 개별 청크 상세 관리 및 부분 번역/재번역
    if total_chunks > 0:
        st.divider()
        with st.expander("개별 청크 상세 관리 및 부분 번역", expanded=True):
            st.caption("각 번역 조각의 진행상황을 확인하고 개별적으로 번역/재번역을 지시하거나 중단할 수 있습니다.")
            is_srt = st.session_state.file_name.endswith(".srt")
            
            glossary_dict = {}
            for item in st.session_state.glossary_data:
                src = item.get("원어 (Source)", "")
                tgt = item.get("번역어 (Target)", "")
                if src and tgt:
                    glossary_dict[str(src).strip()] = str(tgt).strip()
            
            for idx in range(total_chunks):
                is_this_single_active = idx in st.session_state.single_futures and st.session_state.single_futures[idx] is not None and not st.session_state.single_futures[idx].done()
                is_batch_active_on_this = is_batch_running and LIVE_STATUS.current_chunk_idx == idx
                
                with st.container():
                    col_c1, col_c2, col_c3 = st.columns([5, 5, 2])
                    with col_c1:
                        st.text_area(f"청크 {idx+1} 원문", st.session_state.chunks[idx], height=120, key=f"chunk_orig_{idx}", disabled=True)
                    
                    # 개별 청크 번역 필드
                    with col_c2:
                        if is_this_single_active:
                            stream_val = LIVE_STATUS.single_streaming_text.get(idx, "")
                            st.text_area(f"청크 {idx+1} 번역 (실시간 스트리밍...)", stream_val, height=120, key=f"chunk_trans_stream_{idx}", disabled=True)
                        elif is_batch_active_on_this:
                            stream_val = LIVE_STATUS.current_streaming_text
                            st.text_area(f"청크 {idx+1} 번역 (실시간 스트리밍...)", stream_val, height=120, key=f"chunk_trans_stream_{idx}", disabled=True)
                        else:
                            new_trans = st.text_area(f"청크 {idx+1} 번역", st.session_state.translated_chunks[idx], height=120, key=f"chunk_trans_{idx}")
                            if new_trans != st.session_state.translated_chunks[idx]:
                                st.session_state.translated_chunks[idx] = new_trans
                                save_progress_backup()
                                if is_srt:
                                    st.session_state.translated_script = "\n\n".join([c for c in st.session_state.translated_chunks if c])
                                else:
                                    st.session_state.translated_script = "\n".join([c for c in st.session_state.translated_chunks if c])
                    
                    # 액션 및 상태 영역
                    with col_c3:
                        st.markdown("<div style='height: 25px;'></div>", unsafe_allow_html=True)
                        
                        has_translation = bool(st.session_state.translated_chunks[idx].strip())
                        
                        # 3. 진행 상황 확인 (상태 라벨 표시)
                        if is_this_single_active or is_batch_active_on_this:
                            st.info("⏳ 번역 진행 중")
                        elif has_translation:
                            st.success("✅ 번역 완료")
                        else:
                            st.caption("💤 대기 중")
                            
                        # 6. 개별 청크 중단 및 번역/재번역 버튼 제어
                        if is_this_single_active:
                            if st.button("중단", key=f"stop_btn_{idx}", type="primary", use_container_width=True):
                                st.session_state.single_cancel_tokens[idx]["cancel"] = True
                                st.session_state.single_futures[idx] = None
                                if idx in LIVE_STATUS.single_streaming_text:
                                    del LIVE_STATUS.single_streaming_text[idx]
                                st.warning("중지됨")
                                st.rerun()
                        elif is_batch_active_on_this:
                            st.caption("일괄 번역 실행 중")
                        else:
                            btn_label = "부분 재번역" if has_translation else "부분 번역"
                            if st.button(btn_label, key=f"retrans_btn_{idx}", use_container_width=True, disabled=is_batch_running):
                                if not st.session_state.model_loaded:
                                    st.error("모델 로드 필요!")
                                else:
                                    # 단일 청크 번역 등록 및 시작
                                    st.session_state.single_cancel_tokens[idx] = {"cancel": False}
                                    LIVE_STATUS.single_streaming_text[idx] = ""
                                    if idx in LIVE_STATUS.single_completed_translations:
                                        del LIVE_STATUS.single_completed_translations[idx]
                                    
                                    prev_orig = st.session_state.chunks[idx-1] if idx > 0 else ""
                                    prev_trans = st.session_state.translated_chunks[idx-1] if idx > 0 else ""
                                    
                                    from core.translator import build_translation_prompt, build_retranslation_prompt
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
                                        
                                        def run_single_task(model, processor, prompt, chunk_idx, cancel_token, ctx):
                                            from core.translator import translate_one_chunk
                                            from streamlit.runtime.scriptrunner import add_script_run_ctx
                                            import threading
                                            add_script_run_ctx(threading.current_thread(), ctx)

                                            max_retries = 3
                                            clean_txt = None
                                            for retry in range(max_retries):
                                                current_temp = temperature
                                                current_penalty = repetition_penalty
                                                if retry > 0:
                                                    current_temp = min(0.8, temperature + 0.15 * retry)
                                                    current_penalty = repetition_penalty + 0.1 * retry
                                                    LIVE_STATUS.single_streaming_text[chunk_idx] = f"[반복 루프 감지 - 재시도 {retry}/{max_retries-1}...]\n"

                                                def on_token(_token_text, current_text):
                                                    LIVE_STATUS.single_streaming_text[chunk_idx] = current_text
                                                    import time
                                                    now = time.time()
                                                    if not hasattr(LIVE_STATUS, '_last_rerun_time'):
                                                        LIVE_STATUS._last_rerun_time = 0
                                                    if now - LIVE_STATUS._last_rerun_time > 0.1:
                                                        LIVE_STATUS._last_rerun_time = now
                                                        try:
                                                            from streamlit.runtime import get_instance
                                                            runtime = get_instance()
                                                            session_info = runtime._session_mgr.get_active_session_info(ctx.session_id)
                                                            if session_info:
                                                                session_info.session.request_rerun(None)
                                                        except Exception:
                                                            pass

                                                clean_txt = translate_one_chunk(
                                                    model,
                                                    processor,
                                                    prompt,
                                                    temp=current_temp,
                                                    repetition_penalty=current_penalty,
                                                    cancel_token=cancel_token,
                                                    token_callback=on_token,
                                                )
                                                if clean_txt == "__REPETITION_ERROR__":
                                                    if retry < max_retries - 1:
                                                        continue
                                                    else:
                                                        clean_txt = None
                                                        break
                                                elif clean_txt is None:
                                                    break
                                                else:
                                                    break

                                            if clean_txt is None:
                                                return None

                                            LIVE_STATUS.single_completed_translations[chunk_idx] = clean_txt
                                            return clean_txt

                                    single_ctx = get_script_run_ctx()
                                    st.session_state.single_futures[idx] = EXECUTOR.submit(
                                        run_single_task,
                                        st.session_state.model,
                                        st.session_state.processor,
                                        prompt,
                                        idx,
                                        st.session_state.single_cancel_tokens[idx],
                                        single_ctx
                                    )
                                    st.rerun()
                                    
                            if has_translation:
                                st.button(
                                    "번역 지우기",
                                    key=f"clear_btn_{idx}",
                                    use_container_width=True,
                                    disabled=is_batch_running,
                                    on_click=clear_chunk_callback,
                                    args=(idx,)
                                )
                st.divider()

    # 7. 비동기 테스크 실행 중일 때 자동 리프레시 루프 가동
    if is_batch_running or is_single_running:
        import time
        time.sleep(0.5)
        st.rerun()

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
                            st.session_state.persona,
                            list(st.session_state.translated_chunks)
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