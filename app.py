import core.patches
import streamlit as st
from core.utils import LiveStatus
from ui.sidebar import render_sidebar
from ui.tab_script import render_tab_script
from ui.tab_persona import render_tab_persona
from ui.tab_translate import render_tab_translate
from ui.tab_refine import render_tab_refine
from ui.tab_chat import render_tab_chat

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
    /* Google Fonts Import for premium feel */
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&family=Outfit:wght@400;500;600;700;800&display=swap');

    html, body, [data-testid="stAppViewContainer"] {
        font-family: 'Inter', -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
    }

    h1, h2, h3, .main-title {
        font-family: 'Outfit', sans-serif;
    }

    .stTabs [data-baseweb="tab-list"] {
        gap: 8px;
        background-color: rgba(15, 23, 42, 0.05);
        padding: 6px 12px 0 12px;
        border-radius: 12px 12px 0 0;
    }
    .stTabs [data-baseweb="tab"] {
        height: 46px;
        white-space: pre-wrap;
        background-color: transparent;
        border-radius: 8px 8px 0px 0px;
        padding: 8px 16px;
        color: var(--text-color);
        opacity: 0.7;
        font-weight: 500;
        transition: all 0.2s cubic-bezier(0.4, 0, 0.2, 1);
        border: none;
    }
    .stTabs [aria-selected="true"] {
        background-color: rgba(56, 189, 248, 0.1) !important;
        color: #38bdf8 !important;
        opacity: 1;
        font-weight: 700;
        border-bottom: 3px solid #38bdf8 !important;
    }

    /* Modern Premium Card styling */
    .card, .custom-card {
        background-color: var(--secondary-background-color);
        padding: 24px;
        border-radius: 12px;
        border: 1px solid rgba(128, 128, 128, 0.15);
        margin-bottom: 20px;
        box-shadow: 0 4px 12px rgba(0, 0, 0, 0.03);
        transition: all 0.3s ease;
    }
    .card:hover, .custom-card:hover {
        border-color: rgba(56, 189, 248, 0.4);
        box-shadow: 0 8px 24px rgba(56, 189, 248, 0.06);
    }

    /* Status boxes with pastels */
    .status-box {
        padding: 14px 18px;
        border-radius: 10px;
        margin-bottom: 16px;
        font-weight: 600;
        font-size: 14px;
        display: flex;
        align-items: center;
        gap: 8px;
        box-shadow: 0 4px 6px rgba(0, 0, 0, 0.02);
    }
    .status-ok {
        background-color: rgba(16, 185, 129, 0.12);
        color: #10b981;
        border: 1px solid rgba(16, 185, 129, 0.25);
    }
    .status-warn {
        background-color: rgba(245, 158, 11, 0.12);
        color: #f59e0b;
        border: 1px solid rgba(245, 158, 11, 0.25);
    }
    .status-info {
        background-color: rgba(59, 130, 246, 0.12);
        color: #3b82f6;
        border: 1px solid rgba(59, 130, 246, 0.25);
    }
    .workflow-summary {
        display: grid;
        grid-template-columns: repeat(5, minmax(120px, 1fr));
        gap: 10px;
        margin: 14px 0 22px 0;
    }
    .workflow-item {
        border: 1px solid rgba(148, 163, 184, 0.22);
        border-radius: 8px;
        padding: 12px 14px;
        background: rgba(30, 41, 59, 0.55);
        min-height: 76px;
    }
    .workflow-item strong {
        display: block;
        font-size: 13px;
        margin-bottom: 8px;
    }
    .workflow-item span {
        color: #94a3b8;
        font-size: 12px;
        line-height: 1.35;
    }
    .workflow-ready {
        border-color: rgba(16, 185, 129, 0.45);
        background: rgba(16, 185, 129, 0.08);
    }
    .workflow-active {
        border-color: rgba(56, 189, 248, 0.55);
        background: rgba(56, 189, 248, 0.10);
    }
    @media (max-width: 1100px) {
        .workflow-summary {
            grid-template-columns: repeat(2, minmax(0, 1fr));
        }
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
if "rj_code" not in st.session_state:
    st.session_state.rj_code = ""
if "last_loaded_project_dir" not in st.session_state:
    st.session_state.last_loaded_project_dir = ""

# LIVE_STATUS session state initialization
if "LIVE_STATUS" not in st.session_state:
    st.session_state.LIVE_STATUS = LiveStatus()

# Project directory sync check (triggers backup load if project folder changes)
from core.progress_store import get_backup_dir
from core.utils import load_progress_backup

# Automatically inject RJ code prefix into file_name to ensure thread-safe unified folder mapping
if st.session_state.rj_code.strip():
    rj = st.session_state.rj_code.strip().upper()
    if rj not in st.session_state.file_name.upper():
        st.session_state.file_name = f"{rj}_{st.session_state.file_name}"

current_dir = get_backup_dir(st.session_state.file_name)
if st.session_state.last_loaded_project_dir != current_dir:
    st.session_state.last_loaded_project_dir = current_dir
    load_progress_backup(st.session_state.file_name)

# Main Title
st.title("PersonaASMR-Translator")
st.markdown("로컬 MLX VLM (Gemma 4 12B) 기반 ASMR 맞춤형 페르소나 번역 시스템")

script_chars = len(st.session_state.original_script.strip())
glossary_count = len([item for item in st.session_state.glossary_data if item.get("원어 (Source)")])
translated_count = sum(1 for chunk in st.session_state.translated_chunks if chunk.strip())
total_chunks = len(st.session_state.chunks)
persona_ready = any([
    st.session_state.persona.get("tone"),
    st.session_state.persona.get("relationship"),
    st.session_state.persona.get("situation"),
    st.session_state.persona.get("key_rules"),
])

summary_items = [
    ("1. 대본", script_chars > 0, f"{script_chars:,}자 입력됨" if script_chars else "파일 업로드 또는 직접 입력 필요"),
    ("2. 페르소나", persona_ready, "설정됨" if persona_ready else "자동 생성 또는 직접 입력 필요"),
    ("3. 용어집", glossary_count > 0, f"{glossary_count:,}개 적용" if glossary_count else "선택 사항"),
    ("4. 모델", st.session_state.model_loaded, "로드 완료" if st.session_state.model_loaded else "사이드바에서 로드 필요"),
    ("5. 번역", translated_count > 0, f"{translated_count}/{total_chunks} 청크 완료" if total_chunks else "대본 입력 후 준비"),
]
summary_html = "".join(
    f'<div class="workflow-item {"workflow-ready" if ready else ""}"><strong>{title}</strong><span>{detail}</span></div>'
    for title, ready, detail in summary_items
)
st.markdown(f'<div class="workflow-summary">{summary_html}</div>', unsafe_allow_html=True)

# Render Sidebar (returns slider parameters)
params = render_sidebar()

# Render Tab Views
tab1, tab2, tab3, tab4, tab5 = st.tabs([
    "1. 대본 입력",
    "2. 페르소나 및 용어집 설정",
    "3. 번역 실행 및 실시간 보기",
    "4. 교정 및 결과 다운로드",
    "5. AI 롤플레잉 대화 (Chat)"
])

with tab1:
    render_tab_script()
with tab2:
    render_tab_persona()
with tab3:
    render_tab_translate(params)
with tab4:
    render_tab_refine()
with tab5:
    render_tab_chat(params)
