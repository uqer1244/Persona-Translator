import streamlit as st
import os
import re
import json
import shutil
import hashlib

from core.utils import get_backup_dir, list_saved_images, decode_text, natural_sort_key
from core.progress_store import get_image_note_path, load_image_note, BACKUP_ROOT
from ui.library_helpers import (
    get_dir_tree,
    get_display_image_cached,
    get_nsfw_status,
    set_nsfw_status,
)

def render_tab_library():
    if "library_root_dir" not in st.session_state:
        st.session_state.library_root_dir = os.path.abspath("./DLdata")

    st.header("작품 라이브러리")
    st.caption("프로젝트 복원 및 새로운 작품을 격자형 대시보드에서 효율적으로 관리하고 탐색합니다.")

    # 1. Search Bar and Filters
    col_search, col_opts = st.columns([2, 1])
    
    with col_search:
        search_query = st.text_input(
            "작품 검색 (RJ 코드 또는 이름)",
            value="",
            placeholder="검색할 RJ 코드나 작품명을 입력하세요...",
            key="lib_search_query_input"
        )
    
    with col_opts:
        st.markdown("<div style='height: 5px;'></div>", unsafe_allow_html=True)
        col_nsfw_hide, col_nsfw_blur = st.columns(2)
        with col_nsfw_hide:
            nsfw_hide = st.checkbox("NSFW 숨기기", value=False, help="NSFW로 분류된 작품들을 라이브러리에서 숨깁니다.", key="lib_nsfw_hide_cb")
        with col_nsfw_blur:
            nsfw_blur_strength = st.slider(
                "NSFW 블러 강도",
                min_value=0,
                max_value=60,
                value=20,
                step=5,
                help="0으로 두면 NSFW 썸네일 블러가 꺼집니다.",
                key="lib_nsfw_blur_strength_slider"
            )
        blur_enabled = not nsfw_hide and nsfw_blur_strength > 0

    # Sub-tabs for Ongoing Projects vs DLdata Library
    lib_tab1, lib_tab2 = st.tabs(["진행 중인 프로젝트 복원", "신규 작품 가져오기"])

    # -------------------------------------------------------------
    # Tab 1: Ongoing Projects
    # -------------------------------------------------------------
    with lib_tab1:
        project_folders = []
        if os.path.exists(BACKUP_ROOT):
            for name in os.listdir(BACKUP_ROOT):
                full_path = os.path.join(BACKUP_ROOT, name)
                if os.path.isdir(full_path) and not name.startswith(".") and os.path.exists(os.path.join(full_path, "progress.json")):
                    project_folders.append((name, full_path))
        project_folders.sort(key=lambda x: x[0])

        # Apply search filter
        if search_query.strip():
            q = search_query.strip().lower()
            project_folders = [p for p in project_folders if q in p[0].lower()]

        # Apply NSFW filter & compute NSFW status
        filtered_projects = []
        for name, path in project_folders:
            is_nsfw = get_nsfw_status(name, path)
            if nsfw_hide and is_nsfw:
                continue
            filtered_projects.append((name, path, is_nsfw))

        if not filtered_projects:
            if search_query.strip():
                st.info("검색 조건에 맞는 진행 중인 프로젝트가 없습니다.")
            else:
                st.info("진행 중인 번역 프로젝트가 없습니다. '신규 작품 가져오기' 탭에서 작품을 불러오세요.")
        else:
            cols_per_row = 5
            for i in range(0, len(filtered_projects), cols_per_row):
                row_projects = filtered_projects[i:i+cols_per_row]
                cols = st.columns(cols_per_row)
                for idx, (proj_name, proj_path, is_nsfw) in enumerate(row_projects):
                    col = cols[idx]
                    
                    # Find cover image
                    cover_path = None
                    for ext in [".jpg", ".png", ".webp", ".jpeg"]:
                        t_path = os.path.join(proj_path, f"thumbnail{ext}")
                        if os.path.exists(t_path):
                            cover_path = t_path
                            break
                    if not cover_path:
                        images_dir = os.path.join(proj_path, "images")
                        if os.path.exists(images_dir):
                            try:
                                for f in os.listdir(images_dir):
                                    if not f.startswith(".") and os.path.splitext(f)[1].lower() in {".png", ".jpg", ".jpeg", ".webp"}:
                                        cover_path = os.path.join(images_dir, f)
                                        break
                            except Exception:
                                pass

                    with col:
                        # 1. Cover Image (with blur if needed)
                        if cover_path:
                            display_img = get_display_image_cached(cover_path, is_nsfw and blur_enabled, nsfw_blur_strength)
                            st.image(display_img, width='stretch')
                        else:
                            st.markdown(
                                '<div style="height: 120px; background-color: #1e293b; border-radius: 4px; display: flex; align-items: center; justify-content: center; color: #64748b; font-weight: bold; margin-bottom: 8px; font-size: 11px; border: 1px solid #334155;">'
                                'NO THUMBNAIL'
                                '</div>',
                                unsafe_allow_html=True
                            )
                        
                        # 2. Badge & Title
                        badge_html = "<span style='color: #ef4444; font-weight: bold; font-size: 11px;'>[NSFW]</span> " if is_nsfw else ""
                        st.markdown(
                            f"<div style='text-align: center; font-weight: bold; font-size: 13px; margin-bottom: 4px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap;'>{badge_html}{proj_name}</div>",
                            unsafe_allow_html=True
                        )

                        # 3. Restore Button
                        if st.button("복원", key=f"restore_lib_{proj_name}", width='stretch', type="primary"):
                            from core.progress_store import load_progress, load_persona_backup, list_saved_images
                            progress_data = load_progress(proj_name)
                            if progress_data:
                                st.session_state.file_name = progress_data.get("file_name", f"{proj_name}_script.txt")
                                st.session_state.chunks = progress_data.get("original_chunks", [])
                                st.session_state.translated_chunks = progress_data.get("translated_chunks", [])
                                
                                is_srt = st.session_state.file_name.endswith(".srt") or st.session_state.file_name.endswith(".vtt") or st.session_state.file_name.endswith(".lrc")
                                if is_srt:
                                    st.session_state.translated_script = "\n\n".join([c for c in st.session_state.translated_chunks if c])
                                else:
                                    st.session_state.translated_script = "\n".join([c for c in st.session_state.translated_chunks if c])
                                    
                                scenario_path = os.path.join(proj_path, "scenario.txt")
                                if os.path.exists(scenario_path):
                                    try:
                                        with open(scenario_path, "rb") as sf:
                                            raw_data = sf.read()
                                        st.session_state.original_script = decode_text(raw_data)
                                    except Exception:
                                        sep = '\n\n' if is_srt else '\n\n\n'
                                        st.session_state.original_script = sep.join(st.session_state.chunks)
                                else:
                                    sep = '\n\n' if is_srt else '\n\n\n'
                                    st.session_state.original_script = sep.join(st.session_state.chunks)
                                    
                                persona_data = load_persona_backup(proj_name)
                                if persona_data:
                                    st.session_state.persona = persona_data.get("persona", {})
                                    st.session_state.glossary_data = persona_data.get("glossary_data", [])
                                    st.session_state.script_summary = persona_data.get("script_summary", {})
                                
                                try:
                                    from ui.tab_chat import load_chat_history
                                    chat_hist = load_chat_history(proj_name)
                                    if chat_hist:
                                        st.session_state.chat_history = chat_hist
                                        st.session_state.chat_loaded_project = proj_name
                                    else:
                                        st.session_state.chat_history = []
                                        st.session_state.chat_loaded_project = proj_name
                                except Exception:
                                    st.session_state.chat_history = []
                                    st.session_state.chat_loaded_project = proj_name
                                    
                                st.session_state.temp_image_paths = list_saved_images(proj_name)
                                st.session_state.rj_code = proj_name
                                
                                st.toast(f"[{proj_name}] 프로젝트 복원 완료!")
                                st.rerun()

                        # 4. Settings Popover
                        with st.popover("관리", width='stretch'):
                            new_nsfw = st.checkbox("NSFW 지정", value=is_nsfw, key=f"nsfw_chk_{proj_name}")
                            if new_nsfw != is_nsfw:
                                set_nsfw_status(proj_path, new_nsfw)
                                st.toast(f"NSFW 상태가 변경되었습니다: {new_nsfw}")
                                st.rerun()
                                
                            st.markdown("---")
                            confirm_del = st.checkbox("정말 삭제할까요?", value=False, key=f"confirm_del_{proj_name}")
                            if confirm_del:
                                if st.button("영구 삭제 실행", key=f"execute_del_{proj_name}", type="primary", width='stretch'):
                                    try:
                                        shutil.rmtree(proj_path)
                                        st.toast(f"[{proj_name}] 프로젝트가 완전히 삭제되었습니다.")
                                        st.rerun()
                                    except Exception as e:
                                        st.error(f"삭제 실패: {e}")

    with lib_tab2:
        # 보관함 루트 디렉토리 설정 UI
        st.markdown("**보관함 루트 폴더 지정 (DLdata 외 경로 선택 가능)**")
        col_lib_picker, col_lib_path = st.columns([1, 3])
        with col_lib_picker:
            if st.button("보관함 폴더 변경...", key="change_library_root_btn", width='stretch'):
                try:
                    import subprocess
                    import sys
                    python_exe = sys.executable or "python"
                    code = (
                        "import tkinter as tk\n"
                        "from tkinter import filedialog\n"
                        "import os\n"
                        "root = tk.Tk()\n"
                        "root.withdraw()\n"
                        "root.wm_attributes('-topmost', 1)\n"
                        "root.lift()\n"
                        "root.focus_force()\n"
                        "path = filedialog.askdirectory(title='보관함 루트 폴더 선택')\n"
                        "print(path or '')\n"
                        "root.destroy()\n"
                    )
                    res = subprocess.run(
                        [python_exe, "-c", code],
                        capture_output=True,
                        text=True,
                        check=True
                    )
                    selected_dir = res.stdout.strip()
                    if selected_dir and os.path.exists(selected_dir):
                        st.session_state.library_root_dir = selected_dir
                        st.toast(f"보관함 경로가 변경되었습니다: {os.path.basename(selected_dir)}")
                        st.rerun()
                except Exception as e:
                    st.error(f"폴더 탐색기를 열 수 없습니다: {e}")
        with col_lib_path:
            st.text_input(
                "보관함 경로",
                placeholder="/Users/a0000/ASMR_Library",
                label_visibility="collapsed",
                key="library_root_dir"
            )

        dldata_root = os.path.abspath(st.session_state.library_root_dir)
        os.makedirs(dldata_root, exist_ok=True)

        dldata_folders = []
        if os.path.exists(dldata_root):
            for name in os.listdir(dldata_root):
                full_path = os.path.join(dldata_root, name)
                if os.path.isdir(full_path) and not name.startswith("."):
                    dldata_folders.append((name, full_path))
        dldata_folders.sort(key=lambda x: x[0])

        # Filter by search
        if search_query.strip():
            q = search_query.strip().lower()
            dldata_folders = [d for d in dldata_folders if q in d[0].lower()]

        # Filter by NSFW & check status
        filtered_dldata = []
        for name, path in dldata_folders:
            is_nsfw = get_nsfw_status(name, path)
            if nsfw_hide and is_nsfw:
                continue
            filtered_dldata.append((name, path, is_nsfw))

        if "local_folder_input" not in st.session_state:
            st.session_state.local_folder_input = ""

        if not filtered_dldata:
            st.info("DLdata 보관함이 비어 있거나 매칭되는 작품이 없습니다.")
        else:
            st.markdown("**DLdata 보관함 작품 목록**")
            cols_per_row = 5
            for i in range(0, len(filtered_dldata), cols_per_row):
                row_folders = filtered_dldata[i:i+cols_per_row]
                cols = st.columns(cols_per_row)
                for idx, (folder_name, folder_path, is_nsfw) in enumerate(row_folders):
                    col = cols[idx]

                    # Find cover image
                    cover_path = None
                    try:
                        for f in os.listdir(folder_path):
                            if not f.startswith(".") and os.path.splitext(f)[1].lower() in {".png", ".jpg", ".jpeg", ".webp"}:
                                cover_path = os.path.join(folder_path, f)
                                break
                    except Exception:
                        pass

                    # Fallback to projects/images
                    if not cover_path:
                        try:
                            backup_dir = get_backup_dir(folder_name)
                            backup_img_dir = os.path.join(backup_dir, "images")
                            if os.path.exists(backup_img_dir):
                                for f in os.listdir(backup_img_dir):
                                    if not f.startswith(".") and os.path.splitext(f)[1].lower() in {".png", ".jpg", ".jpeg", ".webp"}:
                                        cover_path = os.path.join(backup_img_dir, f)
                                        break
                        except Exception:
                            pass

                    is_selected = (st.session_state.local_folder_input == folder_path)

                    with col:
                        # 1. Cover Image (with blur if needed)
                        if cover_path:
                            display_img = get_display_image_cached(cover_path, is_nsfw and blur_enabled, nsfw_blur_strength)
                            st.image(display_img, width='stretch')
                        else:
                            st.markdown(
                                '<div style="height: 120px; background-color: #334155; border-radius: 4px; display: flex; align-items: center; justify-content: center; color: #94a3b8; font-weight: bold; margin-bottom: 8px; font-size: 11px; border: 1px solid #475569;">'
                                'NO IMAGE'
                                '</div>',
                                unsafe_allow_html=True
                            )

                        # 2. Title and NSFW Badge
                        badge_html = "<span style='color: #ef4444; font-weight: bold; font-size: 11px;'>[NSFW]</span> " if is_nsfw else ""
                        st.markdown(
                            f"<div style='text-align: center; font-weight: bold; font-size: 12px; margin-bottom: 4px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap;'>{badge_html}{folder_name}</div>",
                            unsafe_allow_html=True
                        )

                        # 3. Select Button
                        btn_label = "선택됨" if is_selected else "선택"
                        btn_type = "primary" if is_selected else "secondary"
                        if st.button(btn_label, key=f"select_dldata_{folder_name}", type=btn_type, width='stretch'):
                            if st.session_state.local_folder_input != folder_path:
                                st.session_state.local_folder_input = folder_path
                                from core.progress_store import extract_rj_code
                                rj = extract_rj_code(folder_name)
                                if rj:
                                    st.session_state.rj_code = rj
                                st.rerun()

                        # 4. Settings Popover
                        with st.popover("관리", width='stretch'):
                            new_nsfw = st.checkbox("NSFW 지정", value=is_nsfw, key=f"nsfw_dldata_chk_{folder_name}")
                            if new_nsfw != is_nsfw:
                                set_nsfw_status(folder_path, new_nsfw)
                                st.toast(f"NSFW 상태가 변경되었습니다: {new_nsfw}")
                                st.rerun()

        # -------------------------------------------------------------
        # Selected Folder Scanning Panel
        # -------------------------------------------------------------
        st.markdown("<div style='height: 15px;'></div>", unsafe_allow_html=True)
        st.markdown("### 선택한 로컬 폴더 상세 스캔 및 불러오기")
        
        col_dir_btn, col_dir_path = st.columns([1, 3])

        with col_dir_btn:
            if st.button("폴더 선택...", key="lib_folder_picker_btn", width='stretch'):
                try:
                    import subprocess
                    import sys

                    python_exe = sys.executable or "python"
                    code = (
                        "import tkinter as tk\n"
                        "from tkinter import filedialog\n"
                        "import os\n"
                        "root = tk.Tk()\n"
                        "root.withdraw()\n"
                        "root.wm_attributes('-topmost', 1)\n"
                        "root.lift()\n"
                        "root.focus_force()\n"
                        "path = filedialog.askdirectory(title='ASMR 작품 폴더 선택')\n"
                        "print(path or '')\n"
                        "root.destroy()\n"
                    )

                    res = subprocess.run(
                        [python_exe, "-c", code],
                        capture_output=True,
                        text=True,
                        check=True
                    )
                    selected_dir_path = res.stdout.strip()
                    if selected_dir_path and os.path.exists(selected_dir_path):
                        st.session_state.local_folder_input = selected_dir_path
                        st.toast(f"선택된 폴더: {os.path.basename(selected_dir_path)}")
                        st.rerun()
                except Exception as e:
                    st.error(f"폴더 탐색기를 열 수 없습니다: {e}. 우측에 경로를 수동으로 입력해 주세요.")

        with col_dir_path:
            st.text_input(
                "로컬 폴더 경로",
                placeholder="/Users/a0000/Downloads/RJ123456",
                label_visibility="collapsed",
                key="local_folder_input"
            )

        if st.session_state.local_folder_input.strip():
            local_path = os.path.abspath(os.path.expanduser(st.session_state.local_folder_input.strip()))
            if not os.path.exists(local_path):
                st.error("입력한 경로가 존재하지 않습니다.")
            elif not os.path.isdir(local_path):
                st.error("입력한 경로는 디렉토리가 아닙니다.")
            else:
                # Scan directory
                files_in_dir = []
                for root, dirs, filenames in os.walk(local_path):
                    # Exclude backend-created directories
                    dirs[:] = [d for d in dirs if not d.startswith('.') and d not in ('translation_backup', 'temp_backups', 'images')]
                    for f in filenames:
                        if not f.startswith('.'):
                            if f in ('progress.json', 'persona.json'):
                                continue
                            base, ext = os.path.splitext(f)
                            if not base.lower().endswith('_translated'):
                                files_in_dir.append(os.path.join(root, f))

                script_exts = {".txt", ".srt", ".pdf", ".vtt", ".lrc"}
                image_exts = {".png", ".jpg", ".jpeg", ".webp"}

                scripts_found = [f for f in files_in_dir if os.path.splitext(f)[1].lower() in script_exts]
                images_found = [f for f in files_in_dir if os.path.splitext(f)[1].lower() in image_exts]

                if not scripts_found and not images_found:
                    st.info("폴더 내에 대본(.txt, .srt, .pdf)이나 이미지(.png, .jpg, .jpeg, .webp) 파일이 존재하지 않습니다.")
                else:
                    st.success(f"스캔 완료: 대본 파일 {len(scripts_found)}개, 이미지 파일 {len(images_found)}개 감지됨")

                    # Initialize / sanitize multiselect values in session state to prevent warnings
                    if "last_scanned_folder" not in st.session_state:
                        st.session_state.last_scanned_folder = ""

                    if st.session_state.last_scanned_folder != local_path:
                        st.session_state.last_scanned_folder = local_path
                        if "lib_select_scripts" in st.session_state:
                            del st.session_state["lib_select_scripts"]
                        if "lib_select_images" in st.session_state:
                            del st.session_state["lib_select_images"]

                    if "lib_select_scripts" not in st.session_state:
                        st.session_state["lib_select_scripts"] = scripts_found
                    else:
                        st.session_state["lib_select_scripts"] = [x for x in st.session_state["lib_select_scripts"] if x in scripts_found]

                    if "lib_select_images" not in st.session_state:
                        st.session_state["lib_select_images"] = images_found[:4] if len(images_found) > 4 else images_found
                    else:
                        st.session_state["lib_select_images"] = [x for x in st.session_state["lib_select_images"] if x in images_found]

                    col_l_s, col_l_i = st.columns(2)
                    with col_l_s:
                        selected_local_scripts = st.multiselect(
                            "가져올 대본 파일 선택",
                            options=scripts_found,
                            format_func=lambda x: os.path.relpath(x, local_path),
                            key="lib_select_scripts"
                        )
                    with col_l_i:
                        selected_local_images = st.multiselect(
                            "가져올 소개 이미지 선택",
                            options=images_found,
                            format_func=lambda x: os.path.relpath(x, local_path),
                            key="lib_select_images"
                        )

                    # Representative thumbnail selection
                    thumbnail_option = st.selectbox(
                        "대표 썸네일 이미지 지정",
                        options=["DLsite에서 자동 다운로드"] + [os.path.basename(img) for img in selected_local_images],
                        help="프로젝트 복원 목록 및 홈 화면에 표시할 카드 썸네일 이미지를 지정합니다.",
                        key="lib_thumbnail_opt"
                    )

                    # Folder tree visualization
                    with st.expander("선택한 폴더의 디렉토리 구조", expanded=False):
                        tree_md = get_dir_tree(local_path)
                        st.text(tree_md)

                    # Image Preview
                    with st.expander("스캔된 이미지 미리보기", expanded=False):
                        if images_found:
                            preview_image_path = st.selectbox(
                                "미리볼 이미지 선택",
                                options=images_found,
                                format_func=lambda x: os.path.relpath(x, local_path),
                                key="lib_image_preview_sel"
                            )
                            if preview_image_path:
                                st.image(preview_image_path, width=300)
                        else:
                            st.info("미리 볼 이미지 파일이 없습니다.")

                    # Script Preview
                    with st.expander("스캔된 대본 파일 미리보기", expanded=False):
                        if scripts_found:
                            preview_file_path = st.selectbox(
                                "미리볼 파일 선택",
                                options=scripts_found,
                                format_func=lambda x: os.path.relpath(x, local_path),
                                key="lib_script_preview_sel"
                            )
                            if preview_file_path:
                                try:
                                    preview_content = ""
                                    if preview_file_path.lower().endswith('.pdf'):
                                        from core.document import extract_text_from_pdf
                                        with open(preview_file_path, "rb") as pf:
                                            preview_content = extract_text_from_pdf(pf)[:800]
                                    else:
                                        with open(preview_file_path, "rb") as pf:
                                            raw_data = pf.read()
                                        preview_content = decode_text(raw_data)[:800]

                                    st.code(preview_content, language="plaintext")
                                except Exception as e:
                                    st.error(f"미리보기를 불러올 수 없습니다: {e}")
                        else:
                            st.info("미리 볼 대본 파일이 없습니다.")

                    # Load Button
                    if st.button("선택한 로컬 파일들 불러오기", type="primary", width='stretch', key="lib_load_btn"):
                        combined_text = []
                        srt_count = sum(1 for f in selected_local_scripts if f.endswith(".srt"))
                        vtt_count = sum(1 for f in selected_local_scripts if f.endswith(".vtt"))
                        lrc_count = sum(1 for f in selected_local_scripts if f.endswith(".lrc"))
                        is_srt_mode = srt_count == len(selected_local_scripts)
                        is_vtt_mode = vtt_count == len(selected_local_scripts)
                        is_lrc_mode = lrc_count == len(selected_local_scripts)
                        is_subtitle_mode = is_srt_mode or is_vtt_mode

                        sorted_local_scripts = sorted(selected_local_scripts, key=lambda x: natural_sort_key(os.path.basename(x)))

                        for idx, file_path in enumerate(sorted_local_scripts):
                            base_filename = os.path.basename(file_path)
                            if file_path.lower().endswith('.pdf'):
                                from core.document import extract_text_from_pdf, clean_pdf_linebreaks
                                with open(file_path, "rb") as f:
                                    extracted_text = extract_text_from_pdf(f)
                                # PDF default breaks settings
                                extracted_text = clean_pdf_linebreaks(extracted_text)
                            else:
                                with open(file_path, "rb") as f:
                                    raw_data = f.read()
                                extracted_text = decode_text(raw_data)

                            if len(sorted_local_scripts) > 1:
                                if is_subtitle_mode:
                                    combined_text.append(extracted_text.strip())
                                else:
                                    track_name = f'Track {idx + 1}'
                                    num_match = re.search(r'\d+', base_filename)
                                    if num_match:
                                        track_name = f'Track {num_match.group(0)}'
                                    combined_text.append(f'[{track_name} ({base_filename})]\n{extracted_text.strip()}')
                            else:
                                combined_text.append(extracted_text.strip())

                        sep = '\n\n' if is_subtitle_mode else '\n\n\n'
                        st.session_state.original_script = sep.join(combined_text)

                        if len(sorted_local_scripts) == 1:
                            st.session_state.file_name = os.path.basename(sorted_local_scripts[0])
                        elif sorted_local_scripts:
                            first_name, _ = os.path.splitext(os.path.basename(sorted_local_scripts[0]))
                            ext = '.srt' if is_srt_mode else ('.vtt' if is_vtt_mode else ('.lrc' if is_lrc_mode else '.txt'))
                            st.session_state.file_name = f'{first_name}_외_{len(sorted_local_scripts)-1}개' + ext

                        # Set RJ code
                        from core.progress_store import extract_rj_code
                        rj = extract_rj_code(local_path)
                        if not rj:
                            for sf in sorted_local_scripts:
                                rj = extract_rj_code(os.path.basename(sf))
                                if rj: break
                        if not rj:
                            rj = extract_rj_code(st.session_state.original_script)
                        if rj:
                            st.session_state.rj_code = rj

                        project_dir = get_backup_dir(st.session_state.file_name, create=True)
                        images_dir = os.path.join(project_dir, "images")
                        os.makedirs(images_dir, exist_ok=True)

                        # Process images
                        temp_image_paths = []
                        if selected_local_images:
                            sorted_local_images = sorted(selected_local_images, key=lambda x: natural_sort_key(os.path.basename(x)))
                            for i_idx, img_path in enumerate(sorted_local_images):
                                with open(img_path, "rb") as f:
                                    raw_image = f.read()
                                image_hash = hashlib.sha256(raw_image).hexdigest()[:12]
                                image_stem = os.path.splitext(os.path.basename(img_path))[0]
                                safe_stem = "".join(ch if ch.isalnum() or ch in ("-", "_") else "_" for ch in image_stem)
                                target_img_path = os.path.join(images_dir, f"img_{i_idx}_{safe_stem}_{image_hash}.jpg")
                                try:
                                    image = Image.open(io.BytesIO(raw_image)).convert("RGB")
                                    image.thumbnail((768, 768))
                                    image.save(target_img_path, format="JPEG", quality=82, optimize=True)
                                except Exception:
                                    with open(target_img_path, "wb") as f:
                                        f.write(raw_image)
                                temp_image_paths.append(target_img_path)
                        st.session_state.temp_image_paths = temp_image_paths

                        # Representative Thumbnail
                        if thumbnail_option == "DLsite에서 자동 다운로드":
                            if st.session_state.rj_code:
                                from core.progress_store import download_dlsite_thumbnail
                                download_dlsite_thumbnail(st.session_state.rj_code, project_dir)
                        else:
                            selected_thumb_src = None
                            for img in selected_local_images:
                                if os.path.basename(img) == thumbnail_option:
                                    selected_thumb_src = img
                                    break
                            if selected_thumb_src:
                                try:
                                    ext = os.path.splitext(selected_thumb_src)[1].lower()
                                    target_thumb_path = os.path.join(project_dir, f"thumbnail{ext}")
                                    shutil.copy(selected_thumb_src, target_thumb_path)
                                except Exception as e:
                                    print(f"[Thumbnail Copy Error] {e}")
                            elif st.session_state.rj_code:
                                from core.progress_store import download_dlsite_thumbnail
                                download_dlsite_thumbnail(st.session_state.rj_code, project_dir)

                        # Save progress & persona
                        from core.progress_store import save_progress, save_persona_backup
                        if is_subtitle_mode:
                            from core.document import chunk_srt
                            st.session_state.chunks = chunk_srt(st.session_state.original_script)
                        else:
                            from core.document import chunk_text
                            st.session_state.chunks = chunk_text(st.session_state.original_script)
                        
                        st.session_state.translated_chunks = [""] * len(st.session_state.chunks)
                        save_progress(st.session_state.file_name, st.session_state.chunks, st.session_state.translated_chunks)
                        save_persona_backup(st.session_state.file_name, {}, [])

                        # Auto scan master glossary
                        from core.progress_store import load_master_glossary
                        master = load_master_glossary()
                        matched_glossary = []
                        script_lower = st.session_state.original_script.lower()
                        for item in master:
                            src = item.get("원어 (Source)", "").strip()
                            tgt = item.get("번역어 (Target)", "").strip()
                            if src and src.lower() in script_lower:
                                matched_glossary.append({
                                    "원어 (Source)": src,
                                    "번역어 (Target)": tgt,
                                    "설명/뉘앙스 (Context)": item.get("설명/뉘앙스 (Context)", "")
                                })
                        if matched_glossary:
                            current_keys = {str(item.get("원어 (Source)", "")).strip() for item in st.session_state.glossary_data if item.get("원어 (Source)")}
                            for item in matched_glossary:
                                if item["원어 (Source)"] not in current_keys:
                                    st.session_state.glossary_data.append(item)

                        st.success("로컬 파일 가져오기 및 신규 프로젝트 생성을 완료했습니다! '대본 입력' 탭에서 대본을 검토하세요.")
                        st.rerun()
