import streamlit as st
import os
import re
from core.utils import get_backup_dir, list_saved_images
from core.progress_store import get_image_note_path, load_image_note

def render_tab_script():
    st.header("대본 및 메타데이터 입력")
    
    # PDF 줄바꿈 보정용 체크박스 (공용 옵션)
    clean_pdf_breaks = st.checkbox(
        "PDF 추출 시 줄바꿈 자동 보정", 
        value=True, 
        help="세로쓰기 등으로 인해 잘게 조각난 줄바꿈을 지능적으로 병합하여 번역 품질을 높입니다."
    )
    
    # Meta description
    st.session_state.metadata_text = st.text_area(
        "ASMR 메타데이터 (소개글, 태그 등)", 
        value=st.session_state.metadata_text,
        placeholder="소개글이나 태그 등을 입력해 주세요.",
        height=120
    )
    
    # RJ Code manually input
    st.session_state.rj_code = st.text_input(
        "DLsite 작품 RJ 코드 (선택사항, 예: RJ123456)",
        value=st.session_state.rj_code,
        help="프로젝트 백업 폴더를 RJ 번호 단위로 관리하여 다른 파일명 대본들과 꼬이지 않도록 분류합니다."
    )

    # -------------------------------------------------------------
    # 📂 로컬 폴더 직접 불러오기 (RJ 디렉토리 스캔)
    # -------------------------------------------------------------
    with st.expander("📂 로컬 폴더 직접 불러오기 (DLdata 및 탐색기 스캔)", expanded=False):
        st.caption("DLdata 보관함의 작품 폴더를 선택하거나 컴퓨터의 로컬 폴더를 직접 선택하여 불러옵니다.")
        
        # 1. Scan DLdata folders automatically
        dldata_root = os.path.abspath("./DLdata")
        os.makedirs(dldata_root, exist_ok=True)
        
        dldata_folders = []
        if os.path.exists(dldata_root):
            for name in os.listdir(dldata_root):
                full_path = os.path.join(dldata_root, name)
                if os.path.isdir(full_path) and not name.startswith("."):
                    dldata_folders.append(name)
        dldata_folders.sort()
        
        # Search box to filter folders
        search_query = st.text_input(
            "🔍 작품 검색 (RJ 번호)",
            value="",
            placeholder="검색할 RJ 번호를 입력하세요..."
        )
        
        filtered_folders = dldata_folders
        if search_query.strip():
            q = search_query.strip().lower()
            filtered_folders = [f for f in dldata_folders if q in f.lower()]
            
        if "local_folder_input" not in st.session_state:
            st.session_state.local_folder_input = ""

        # Render cover art grid
        if filtered_folders:
            st.markdown("**📦 DLdata 보관함 작품 목록**")
            cols_per_row = 5
            for i in range(0, len(filtered_folders), cols_per_row):
                row_folders = filtered_folders[i:i+cols_per_row]
                cols = st.columns(cols_per_row)
                for idx, folder_name in enumerate(row_folders):
                    col = cols[idx]
                    folder_path = os.path.join(dldata_root, folder_name)
                    
                    # Find cover image inside DLdata/RJXXXXXX
                    cover_path = None
                    try:
                        for f in os.listdir(folder_path):
                            if not f.startswith(".") and os.path.splitext(f)[1].lower() in {".png", ".jpg", ".jpeg", ".webp"}:
                                cover_path = os.path.join(folder_path, f)
                                break
                    except Exception:
                        pass
                    
                    # If not found inside folder, look inside temp_backups/RJXXXXXX/images/
                    if not cover_path:
                        try:
                            from core.utils import get_backup_dir
                            # Generate backup dir name safely
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
                        # Draw cover or placeholder
                        if cover_path:
                            st.image(cover_path, width="stretch")
                        else:
                            st.markdown(
                                '<div style="height: 120px; background-color: #334155; border-radius: 4px; display: flex; align-items: center; justify-content: center; color: #94a3b8; font-weight: bold; margin-bottom: 8px; font-size: 11px; border: 1px solid #475569;">'
                                'NO IMAGE'
                                '</div>',
                                unsafe_allow_html=True
                            )
                        
                        # Title
                        st.markdown(
                            f"<div style='text-align: center; font-weight: bold; font-size: 12px; margin-bottom: 4px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap;'>{folder_name}</div>", 
                            unsafe_allow_html=True
                        )
                        
                        # Select button
                        btn_label = "🟢 선택됨" if is_selected else "선택"
                        btn_type = "primary" if is_selected else "secondary"
                        if st.button(btn_label, key=f"select_dldata_grid_{folder_name}", type=btn_type, width="stretch"):
                            if st.session_state.local_folder_input != folder_path:
                                st.session_state.local_folder_input = folder_path
                                from core.progress_store import extract_rj_code
                                rj = extract_rj_code(folder_name)
                                if rj:
                                    st.session_state.rj_code = rj
                                st.rerun()
        else:
            st.info("검색어에 매칭되는 작품이 없거나 DLdata 폴더가 비어 있습니다.")
                
        st.markdown("<div style='height: 8px;'></div>", unsafe_allow_html=True)
        st.markdown("<small><b>기타 외부 폴더 직접 선택 (DLdata 외부 경로)</b></small>", unsafe_allow_html=True)
        
        col_dir_btn, col_dir_path = st.columns([1, 3])
            
        with col_dir_btn:
            if st.button("📁 폴더 선택...", width="stretch"):
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
                        st.toast(f"선택된 폴더: {os.path.basename(selected_dir_path)}", icon="📂")
                        st.rerun()
                except Exception as e:
                    st.error(f"폴더 탐색기를 열 수 없습니다: {e}. 우측에 경로를 수동으로 입력해 주세요.")
                    
        with col_dir_path:
            local_folder = st.text_input(
                "로컬 폴더 경로",
                value=st.session_state.local_folder_input,
                placeholder="/Users/a0000/Downloads/RJ123456",
                label_visibility="collapsed"
            )
            st.session_state.local_folder_input = local_folder
        
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
                    dirs[:] = [d for d in dirs if not d.startswith('.')]
                    for f in filenames:
                        if not f.startswith('.'):
                            files_in_dir.append(os.path.join(root, f))
                
                script_exts = {".txt", ".srt", ".pdf"}
                image_exts = {".png", ".jpg", ".jpeg", ".webp"}
                
                scripts_found = [f for f in files_in_dir if os.path.splitext(f)[1].lower() in script_exts]
                images_found = [f for f in files_in_dir if os.path.splitext(f)[1].lower() in image_exts]
                
                if not scripts_found and not images_found:
                    st.info("폴더 내에 대본(.txt, .srt, .pdf)이나 이미지(.png, .jpg, .jpeg, .webp) 파일이 존재하지 않습니다.")
                else:
                    st.success(f"스캔 완료: 대본 파일 {len(scripts_found)}개, 이미지 파일 {len(images_found)}개 감지됨")
                    
                    col_l_s, col_l_i = st.columns(2)
                    with col_l_s:
                        selected_local_scripts = st.multiselect(
                            "가져올 대본 파일 선택",
                            options=scripts_found,
                            default=scripts_found,
                            format_func=lambda x: os.path.relpath(x, local_path)
                        )
                    with col_l_i:
                        selected_local_images = st.multiselect(
                            "가져올 소개 이미지 선택",
                            options=images_found,
                            default=images_found[:4] if len(images_found) > 4 else images_found,
                            format_func=lambda x: os.path.relpath(x, local_path)
                        )
                        
                    if st.button("선택한 로컬 파일들 불러오기", type="primary", width="stretch"):
                        # Combine scripts
                        combined_text = []
                        is_srt_mode = all(f.endswith(".srt") for f in selected_local_scripts)
                        sorted_local_scripts = sorted(selected_local_scripts)
                        
                        for idx, file_path in enumerate(sorted_local_scripts):
                            base_filename = os.path.basename(file_path)
                            if file_path.endswith('.pdf'):
                                from core.translator import extract_text_from_pdf, clean_pdf_linebreaks
                                with open(file_path, "rb") as f:
                                    extracted_text = extract_text_from_pdf(f)
                                if clean_pdf_breaks:
                                    extracted_text = clean_pdf_linebreaks(extracted_text)
                            else:
                                with open(file_path, "rb") as f:
                                    raw_data = f.read()
                                try:
                                    extracted_text = raw_data.decode('utf-8')
                                except UnicodeDecodeError:
                                    try:
                                        extracted_text = raw_data.decode('cp949')
                                    except UnicodeDecodeError:
                                        extracted_text = raw_data.decode('latin1')
                                        
                            if len(sorted_local_scripts) > 1:
                                if is_srt_mode:
                                    combined_text.append(extracted_text.strip())
                                else:
                                    track_name = f'Track {idx + 1}'
                                    num_match = re.search(r'\d+', base_filename)
                                    if num_match:
                                        track_name = f'Track {num_match.group(0)}'
                                    combined_text.append(f'[{track_name} ({base_filename})]\n{extracted_text.strip()}')
                            else:
                                combined_text.append(extracted_text.strip())
                                
                        sep = '\n\n' if is_srt_mode else '\n\n\n'
                        st.session_state.original_script = sep.join(combined_text)
                        
                        if len(sorted_local_scripts) == 1:
                            st.session_state.file_name = os.path.basename(sorted_local_scripts[0])
                        elif sorted_local_scripts:
                            first_name, _ = os.path.splitext(os.path.basename(sorted_local_scripts[0]))
                            st.session_state.file_name = f'{first_name}_외_{len(sorted_local_scripts)-1}개' + ('.srt' if is_srt_mode else '.txt')
                        
                        # Process images
                        if selected_local_images:
                            # Auto set project dir based on filename or RJ code
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
                                
                            project_dir = get_backup_dir(st.session_state.file_name)
                            images_dir = os.path.join(project_dir, "images")
                            os.makedirs(images_dir, exist_ok=True)
                            
                            temp_image_paths = []
                            for i_idx, img_path in enumerate(selected_local_images):
                                with open(img_path, "rb") as f:
                                    raw_image = f.read()
                                import hashlib
                                image_hash = hashlib.sha256(raw_image).hexdigest()[:12]
                                image_stem = os.path.splitext(os.path.basename(img_path))[0]
                                safe_stem = "".join(ch if ch.isalnum() or ch in ("-", "_") else "_" for ch in image_stem)
                                target_img_path = os.path.join(images_dir, f"img_{i_idx}_{safe_stem}_{image_hash}.jpg")
                                try:
                                    from PIL import Image
                                    import io
                                    image = Image.open(io.BytesIO(raw_image)).convert("RGB")
                                    image.thumbnail((768, 768))
                                    image.save(target_img_path, format="JPEG", quality=82, optimize=True)
                                except Exception:
                                    with open(target_img_path, "wb") as f:
                                        f.write(raw_image)
                                temp_image_paths.append(target_img_path)
                            st.session_state.temp_image_paths = temp_image_paths
                            
                        # Scan for master glossary matches
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
                                    
                        st.success("선택한 로컬 파일들을 스캔하여 불러오기 완료했습니다!")
                        st.rerun()

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
                cols[idx].image(img_file, caption=img_file.name, width="stretch")
    elif st.session_state.temp_image_paths:
        # 이미 백업 폴더에 저장되어 있는 이미지 표시
        st.markdown("**불러온 백업 소개 이미지 미리보기**")
        max_cols_per_row = 4
        num_images = len(st.session_state.temp_image_paths)
        for i in range(0, num_images, max_cols_per_row):
            row_paths = st.session_state.temp_image_paths[i:i + max_cols_per_row]
            cols = st.columns(len(row_paths))
            for idx, img_path in enumerate(row_paths):
                cols[idx].image(img_path, caption=os.path.basename(img_path), width="stretch")
    

    
    if uploaded_files:
        if st.button("업로드된 대본 파일 파싱 및 불러오기", type="primary", width="stretch"):
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
            
            # RJ 코드 자동 추출 반영
            from core.progress_store import extract_rj_code
            rj = extract_rj_code(st.session_state.file_name)
            if not rj:
                rj = extract_rj_code(st.session_state.original_script)
            if not rj:
                rj = extract_rj_code(st.session_state.metadata_text)
            if rj:
                st.session_state.rj_code = rj
            
            if len(sorted_files) == 1:
                st.session_state.file_name = sorted_files[0].name
            else:
                first_name, _ = os.path.splitext(sorted_files[0].name)
                st.session_state.file_name = f'{first_name}_외_{len(sorted_files)-1}개' + ('.srt' if is_srt_mode else '.txt')
                
            # 마스터 단어장에서 용어 자동 매칭 (Scan & 선탑재)
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
                # Merge matched glossary into current glossary_data without duplicates
                current_keys = {str(item.get("원어 (Source)", "")).strip() for item in st.session_state.glossary_data if item.get("원어 (Source)")}
                for item in matched_glossary:
                    if item["원어 (Source)"] not in current_keys:
                        st.session_state.glossary_data.append(item)
                st.toast(f"마스터 단어장에서 {len(matched_glossary)}개 용어를 자동으로 감지해 탑재했습니다!", icon="📚")
                
            st.success(f"총 {len(sorted_files)}개 대본 파일에서 텍스트를 추출하고 병합했습니다! ({len(st.session_state.original_script)} 자)")
            st.rerun()
            
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
