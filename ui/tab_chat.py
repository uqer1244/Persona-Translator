import json

import streamlit as st

from core.bot_card import export_charx_bytes, generate_bot_card
from core.bot_card_storage import load_project_bot_card
from core.progress_store import list_saved_personas, safe_project_name


def _card_filename(card: dict, ext: str) -> str:
    name = card.get("data", {}).get("name", "bot_card")
    safe = "".join(ch if ch.isalnum() or ch in ("_", "-") else "_" for ch in name).strip("_")
    return f"{safe or 'bot_card'}.{ext}"


def render_tab_chat(params: dict):
    st.header("대본 이해 기반 RisuAI 봇카드 제작")
    st.caption("전체 대본을 한 번에 KV 캐시에 올리지 않고, 청크별 분석 결과를 캐싱한 뒤 RisuAI 카드 필드로 합성합니다.")

    if "bot_card_preview" not in st.session_state:
        st.session_state.bot_card_preview = None

    saved_projects = list_saved_personas()
    current_project = safe_project_name(st.session_state.file_name)
    if current_project not in saved_projects and st.session_state.original_script.strip():
        saved_projects = [current_project] + saved_projects

    if not saved_projects:
        st.info("봇카드를 만들 프로젝트가 없습니다. 먼저 대본을 불러오고 페르소나/진행도를 저장해 주세요.")
        return

    default_index = saved_projects.index(current_project) if current_project in saved_projects else 0
    left, right = st.columns([1, 1])

    with left:
        selected_project = st.selectbox(
            "봇카드를 만들 프로젝트",
            options=saved_projects,
            index=default_index,
            help="projects/ 하위에 저장된 progress.json과 persona.json을 기반으로 분석합니다.",
        )
        card_name = st.text_input("카드 이름", value=selected_project)
        prefer_translated = st.checkbox("번역본 우선 사용", value=True, help="번역 완료 청크가 있으면 한국어 번역본을 분석하고, 없으면 원문을 사용합니다.")
        max_chunks_enabled = st.checkbox("테스트용 청크 수 제한", value=False)
        max_chunks = None
        if max_chunks_enabled:
            max_chunks = st.number_input("분석할 최대 청크 수", min_value=1, max_value=200, value=5, step=1)

        can_generate = bool(st.session_state.model_loaded and selected_project)
        if not st.session_state.model_loaded:
            st.warning("사이드바에서 모델을 먼저 로드해야 대본 전체 분석을 실행할 수 있습니다.")

        if st.button("대본 전체 분석으로 봇카드 생성", type="primary", width="stretch", disabled=not can_generate):
            progress_bar = st.progress(0.0)
            status = st.empty()

            def update_progress(idx: int, total: int, stage: str):
                if stage == "synthesis":
                    progress_bar.progress(1.0)
                    status.info("청크 분석 완료. 봇카드 최종 합성 중...")
                else:
                    progress_bar.progress(idx / max(total, 1))
                    status.info(f"대본 청크 분석 중: {idx + 1}/{total}")

            with st.spinner("대본 전체를 저메모리 방식으로 읽고 봇카드를 만드는 중..."):
                card = generate_bot_card(
                    st.session_state.model,
                    st.session_state.processor,
                    project_name=selected_project,
                    metadata_text=st.session_state.get("metadata_text", ""),
                    prefer_translated=prefer_translated,
                    max_chunks=int(max_chunks) if max_chunks else None,
                    card_name=card_name,
                    progress_callback=update_progress,
                )
                st.session_state.bot_card_preview = card
                st.success("봇카드 생성 완료")

    with right:
        card = st.session_state.bot_card_preview or load_project_bot_card(selected_project)
        if not card:
            st.info("아직 생성된 봇카드가 없습니다. 왼쪽에서 생성 버튼을 눌러 주세요.")
            return

        data = card.get("data", {})
        st.subheader(data.get("name", "Bot Card"))
        st.markdown("#### 첫 메시지")
        st.text_area("first_mes", value=data.get("first_mes", ""), height=130, disabled=True, label_visibility="collapsed")

        st.markdown("#### 시나리오")
        st.text_area("scenario", value=data.get("scenario", ""), height=150, disabled=True, label_visibility="collapsed")

        st.markdown("#### 캐릭터 설명")
        st.text_area("description", value=data.get("description", ""), height=260, disabled=True, label_visibility="collapsed")

        entries = data.get("character_book", {}).get("entries", [])
        st.markdown(f"#### 로어북 항목 {len(entries)}개")
        for entry in entries[:8]:
            keys = ", ".join(entry.get("keys", []))
            st.markdown(f"- **{entry.get('name', keys)}**: `{keys}`")
        if len(entries) > 8:
            st.caption(f"외 {len(entries) - 8}개 항목")

        json_bytes = json.dumps(card, ensure_ascii=False, indent=2).encode("utf-8")
        st.download_button(
            "card.json 다운로드",
            data=json_bytes,
            file_name=_card_filename(card, "json"),
            mime="application/json",
            width="stretch",
        )

        charx_bytes = export_charx_bytes(card)
        st.download_button(
            ".charx 다운로드",
            data=charx_bytes,
            file_name=_card_filename(card, "charx"),
            mime="application/octet-stream",
            width="stretch",
        )
