import streamlit as st
import os
import pandas as pd
from core.utils import EXECUTOR, extract_script_structure
from core.progress_store import (
    load_master_glossary,
    save_master_glossary,
    merge_glossaries,
    save_persona_backup,
    list_saved_personas,
    load_persona_by_project_name,
    load_image_note,
    get_image_note_path
)
from core.analyzer import analyze_persona

def render_tab_persona():
    st.header("페르소나 및 용어집 설정")
    
    col1, col2 = st.columns(2)
    
    with col1:
        st.subheader("캐릭터 페르소나 설정")
        st.caption("대본 번역 시 적용할 캐릭터의 어투와 성격 규칙입니다.")
        
        # Persona analyze button
        if st.button("페르소나 및 용어집 자동 생성", width="stretch"):
            if not st.session_state.model_loaded:
                st.error("먼저 사이드바에서 모델을 로드해주세요!")
            elif not st.session_state.original_script and not st.session_state.metadata_text:
                st.error("페르소나 분석을 위해 대본 원문이나 메타데이터를 입력해 주세요.")
            else:
                script_preview = extract_script_structure(
                    st.session_state.original_script,
                    file_name=st.session_state.file_name,
                    max_total_chars=3000
                )
                with st.spinner("AI가 대본과 메타데이터를 분석하여 페르소나를 도출 중입니다..."):
                    try:
                        # Load existing master glossary to feed into LLM for incremental extraction
                        master = load_master_glossary()
                        
                        future = EXECUTOR.submit(
                            analyze_persona,
                            st.session_state.model,
                            st.session_state.processor,
                            st.session_state.metadata_text,
                            script_preview,
                            st.session_state.temp_image_paths,
                            master
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
                                src = item.get("source") or item.get("원어") or ""
                                tgt = item.get("target") or item.get("번역어") or ""
                                desc = item.get("context") or item.get("설명") or item.get("뉘앙스") or ""
                                if src and tgt:
                                    new_glossary.append({
                                        "원어 (Source)": src,
                                        "번역어 (Target)": tgt,
                                        "설명/뉘앙스 (Context)": desc
                                    })
                            if new_glossary:
                                # Merge VLM new glossary items into current glossary_data without duplicates
                                current_keys = {str(item.get("원어 (Source)", "")).strip() for item in st.session_state.glossary_data if item.get("원어 (Source)")}
                                for item in new_glossary:
                                    if item["원어 (Source)"] not in current_keys:
                                        st.session_state.glossary_data.append(item)
                                        
                        st.success("페르소나 및 신규 용어집 자동 추출 완료!")
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
        
        # Normalize current glossary_data to have the columns we want
        normalized_glossary = []
        for item in st.session_state.glossary_data:
            src = item.get("원어 (Source)") or item.get("원어 (영문/일문 등)") or ""
            tgt = item.get("번역어 (Target)") or item.get("고정 번역어 (한글)") or ""
            ctx = item.get("설명/뉘앙스 (Context)") or ""
            normalized_glossary.append({
                "원어 (Source)": src,
                "번역어 (Target)": tgt,
                "설명/뉘앙스 (Context)": ctx
            })
        st.session_state.glossary_data = normalized_glossary

        glossary_df = pd.DataFrame(st.session_state.glossary_data)
        if glossary_df.empty:
            glossary_df = pd.DataFrame(columns=["원어 (Source)", "번역어 (Target)", "설명/뉘앙스 (Context)"])
        
        # Streamlit interactive data editor
        edited_df = st.data_editor(
            glossary_df, 
            num_rows="dynamic",
            width="stretch",
            column_config={
                "원어 (Source)": st.column_config.TextColumn("원어 (영문/일문 등)", help="원본 텍스트 내 매칭 단어", required=True),
                "번역어 (Target)": st.column_config.TextColumn("고정 번역어 (한글)", help="출력될 한글 단어", required=True),
                "설명/뉘앙스 (Context)": st.column_config.TextColumn("설명 및 뉘앙스", help="어떤 뉘앙스로 변환되어야 하는지 정보 기입 (선택사항)")
            }
        )
        st.session_state.glossary_data = edited_df.to_dict(orient="records")

        # Merge to Master Glossary button
        st.markdown("<div style='height: 10px;'></div>", unsafe_allow_html=True)
        if st.button("💾 현재 용어들을 마스터 단어장에 누적 병합 및 저장", width="stretch"):
            master = load_master_glossary()
            merged = merge_glossaries(master, st.session_state.glossary_data)
            save_master_glossary(merged)
            st.success(f"현재 프로젝트의 용어 목록이 마스터 단어장(master_glossary.json)에 성공적으로 누적 저장되었습니다! (총 {len(merged)}개 용어)")

    # 📚 마스터 단어장 전역 관리 섹션 (Data Editor)
    st.markdown("<div style='height: 15px;'></div>", unsafe_allow_html=True)
    with st.expander("📚 마스터 단어장 데이터베이스 관리 (전역 적용)", expanded=False):
        st.caption("여러 프로젝트에서 공통으로 적용되는 전역 단어장(master_glossary.json)의 단어 목록입니다. 직접 추가, 삭제, 수정이 가능합니다.")
        master_list = load_master_glossary()
        master_df = pd.DataFrame(master_list)
        if master_df.empty:
            master_df = pd.DataFrame(columns=["원어 (Source)", "번역어 (Target)", "설명/뉘앙스 (Context)"])

        edited_master_df = st.data_editor(
            master_df,
            num_rows="dynamic",
            width="stretch",
            key="master_glossary_editor",
            column_config={
                "원어 (Source)": st.column_config.TextColumn("원어", required=True),
                "번역어 (Target)": st.column_config.TextColumn("고정 번역어 (한글)", required=True),
                "설명/뉘앙스 (Context)": st.column_config.TextColumn("설명 및 뉘앙스")
            }
        )
        
        if st.button("마스터 단어장 변경 사항 저장", type="primary"):
            new_master_list = edited_master_df.to_dict(orient="records")
            save_master_glossary(new_master_list)
            st.success("마스터 단어장(master_glossary.json)을 저장 완료했습니다!")
            st.rerun()

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
                    st.image(img_path, width="stretch")
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
        if st.button("설정 불러오기", width="stretch", disabled=(selected_proj == "선택 안 함")):
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
