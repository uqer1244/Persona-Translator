import streamlit as st
from core.utils import LiveStatus
from ui.sidebar import render_sidebar
from ui.tab_script import render_tab_script
from ui.tab_persona import render_tab_persona
from ui.tab_translate import render_tab_translate
from ui.tab_refine import render_tab_refine

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
st.markdown("로컬 MLX VLM (Gemma 4 12B) 기반 NSFW ASMR 맞춤형 페르소나 번역 시스템")

# Render Sidebar (returns slider parameters)
params = render_sidebar()

# Render Tab Views
tab1, tab2, tab3, tab4 = st.tabs([
    "1. 대본 입력",
    "2. 페르소나 및 용어집 설정",
    "3. 번역 실행 및 실시간 보기",
    "4. 교정 및 결과 다운로드"
])

with tab1:
    render_tab_script()
with tab2:
    render_tab_persona()
with tab3:
    render_tab_translate(params)
with tab4:
    render_tab_refine()