import streamlit as st
import os
from core.utils import EXECUTOR, get_backup_dir

def render_tab_refine():
    st.header("최종 결과 검토 및 교정")
    has_result = bool(st.session_state.translated_script.strip())
    
    st.session_state.translated_script = st.text_area(
        "최종 번역 결과물",
        value=st.session_state.translated_script,
        height=350
    )
    has_result = bool(st.session_state.translated_script.strip())
    st.caption(f"현재 결과물 {len(st.session_state.translated_script.strip()):,}자")
    
    col_ref, col_down = st.columns(2)
    
    with col_ref:
        st.subheader("말투 및 포맷 자동 교정 (Refiner)")
        st.caption("문장의 어조 일관성을 잡고 괄호 매칭 에러 등을 보정합니다.")
        if st.button("후처리 교정 실행", width="stretch", disabled=not has_result):
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
        st.subheader("파일 저장 및 다운로드")
        st.caption("번역 및 교정이 완료된 파일을 로컬 컴퓨터로 다운로드하거나 즉시 저장합니다.")
        
        base_name, ext = os.path.splitext(st.session_state.file_name)
        download_name = f"{base_name}_translated{ext}"
        
        # 1. 브라우저로 다운로드
        st.download_button(
            label="브라우저를 통해 다운로드",
            data=st.session_state.translated_script,
            file_name=download_name,
            mime="text/plain" if not ext == ".srt" else "text/srt",
            width="stretch",
            disabled=not has_result
        )
        
        # 📂 DLdata 작품 폴더 연동 및 저장
        from core.progress_store import extract_rj_code
        rj_code = st.session_state.rj_code.strip().upper() if ("rj_code" in st.session_state and st.session_state.rj_code) else extract_rj_code(st.session_state.file_name)
        
        if rj_code:
            st.divider()
            st.markdown(f"##### DLdata 폴더 연동 (`{rj_code}`)")
            dldata_root = os.path.abspath("./DLdata")
            os.makedirs(dldata_root, exist_ok=True)
            target_dldata_dir = os.path.join(dldata_root, rj_code)
            
            if os.path.exists(target_dldata_dir) and os.path.isdir(target_dldata_dir):
                st.markdown(f'<div class="status-box status-ok" style="font-size: 13px; font-weight: normal; padding: 8px; margin-bottom: 8px;"><b>DLdata 폴더 감지됨</b><br>경로: <code>{target_dldata_dir}</code></div>', unsafe_allow_html=True)
                
                if st.button("DLdata 폴더에 번역본 및 백업 자동 내보내기", width="stretch", type="primary", disabled=not has_result):
                    try:
                        # 1. Save translation text
                        dldata_save_path = os.path.join(target_dldata_dir, download_name)
                        with open(dldata_save_path, "w", encoding="utf-8") as f:
                            f.write(st.session_state.translated_script)
                        
                        # 2. Copy progress.json and persona.json if they exist
                        import shutil
                        from core.progress_store import get_backup_path, get_persona_backup_path
                        
                        translation_backup_dir = os.path.join(target_dldata_dir, "translation_backup")
                        os.makedirs(translation_backup_dir, exist_ok=True)
                        
                        prog_path = get_backup_path(st.session_state.file_name)
                        if os.path.exists(prog_path):
                            shutil.copy(prog_path, os.path.join(translation_backup_dir, "progress.json"))
                            
                        pers_path = get_persona_backup_path(st.session_state.file_name)
                        if os.path.exists(pers_path):
                            shutil.copy(pers_path, os.path.join(translation_backup_dir, "persona.json"))
                            
                        st.success(f"성공적으로 내보냈습니다!\n\n* 번역본 저장: `{dldata_save_path}`\n* 백업 아카이빙 완료: `{translation_backup_dir}/`")
                    except Exception as e:
                        st.error(f"DLdata 저장 중 오류 발생: {e}")
            else:
                st.markdown(f'<div class="status-box status-warn" style="font-size: 13px; font-weight: normal; padding: 8px; margin-bottom: 8px;"><b>DLdata 내 작품 폴더 없음</b><br>경로: <code>{target_dldata_dir}</code></div>', unsafe_allow_html=True)
                if st.button(f"DLdata에 {rj_code} 폴더 직접 생성", width="stretch"):
                    try:
                        os.makedirs(target_dldata_dir, exist_ok=True)
                        st.success(f"폴더를 성공적으로 생성했습니다: `{target_dldata_dir}`")
                        st.rerun()
                    except Exception as e:
                        st.error(f"폴더 생성 중 오류 발생: {e}")
        
        st.divider()
        
        # 2. 프로젝트 백업 폴더에 즉시 저장
        project_dir = get_backup_dir(st.session_state.file_name)
        backup_save_path = os.path.join(project_dir, download_name)
        
        if st.button("프로젝트 백업 폴더에 즉시 저장", width="stretch", disabled=not has_result):
            try:
                with open(backup_save_path, "w", encoding="utf-8") as f:
                    f.write(st.session_state.translated_script)
                st.success(f"프로젝트 폴더에 저장되었습니다!\n\n저장 경로: `{backup_save_path}`")
            except Exception as e:
                st.error(f"저장 중 오류 발생: {e}")
                
        # 3. 사용자 정의 로컬 경로에 저장
        st.markdown("##### 사용자 정의 로컬 경로에 저장")
        default_custom_path = os.path.expanduser(f"~/Downloads/{download_name}")
        custom_save_path = st.text_input(
            "저장할 절대 경로 입력",
            value=default_custom_path,
            help="원하는 로컬 폴더 및 파일명을 절대 경로로 지정하십시오."
        )
        
        if st.button("지정 경로에 파일로 저장", width="stretch", disabled=not has_result):
            if not custom_save_path.strip():
                st.error("올바른 저장 경로를 입력해 주세요.")
            else:
                try:
                    target_path = os.path.abspath(os.path.expanduser(custom_save_path.strip()))
                    os.makedirs(os.path.dirname(target_path), exist_ok=True)
                    with open(target_path, "w", encoding="utf-8") as f:
                        f.write(st.session_state.translated_script)
                    st.success(f"지정된 경로에 저장되었습니다!\n\n저장 경로: `{target_path}`")
                except Exception as e:
                    st.error(f"저장 중 오류 발생: {e}")
