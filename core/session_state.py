import streamlit as st

from core.progress_store import get_backup_dir


DEFAULT_PERSONA = {
    "tone": "",
    "relationship": "",
    "situation": "",
    "key_rules": [],
}

DEFAULT_SCRIPT_SUMMARY = {
    "speaker_name": "미분석",
    "listener_role": "미분석",
    "situation": "대본 분석 전입니다.",
    "story": "대본 분석 전입니다.",
}

SESSION_DEFAULTS = {
    "model_loaded": False,
    "model": None,
    "processor": None,
    "model_runtime": None,
    "persona": DEFAULT_PERSONA,
    "original_script": "",
    "metadata_text": "",
    "translated_script": "",
    "glossary_data": [],
    "file_name": "script.txt",
    "temp_image_paths": [],
    "script_summary": DEFAULT_SCRIPT_SUMMARY,
    "image_generation_prompt": "",
    "chunks": [],
    "translated_chunks": [],
    "batch_future": None,
    "batch_cancel_token": {"cancel": False},
    "single_futures": {},
    "single_cancel_tokens": {},
    "rj_code": "",
    "last_loaded_project_dir": "",
    "bot_card": {},
    "bot_card_preview": None,
}



def initialize_session_state() -> None:
    from core.utils import LiveStatus
    
    for key, default_value in SESSION_DEFAULTS.items():
        if key not in st.session_state:
            if isinstance(default_value, dict):
                st.session_state[key] = default_value.copy()
            elif isinstance(default_value, list):
                st.session_state[key] = default_value.copy()
            else:
                st.session_state[key] = default_value

    if "LIVE_STATUS" not in st.session_state:
        st.session_state.LIVE_STATUS = LiveStatus()



def sync_project_from_session() -> None:
    """Keep the active project folder aligned with the current filename/RJ code."""
    from core.utils import load_progress_backup
    
    if st.session_state.rj_code.strip():
        rj = st.session_state.rj_code.strip().upper()
        if rj not in st.session_state.file_name.upper():
            st.session_state.file_name = f"{rj}_{st.session_state.file_name}"

    current_dir = get_backup_dir(st.session_state.file_name)
    if st.session_state.last_loaded_project_dir != current_dir:
        st.session_state.last_loaded_project_dir = current_dir
        load_progress_backup(st.session_state.file_name)
