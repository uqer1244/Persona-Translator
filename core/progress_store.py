import json
import hashlib
import os
import re


BACKUP_ROOT = os.path.abspath("./projects")

def extract_rj_code(text: str) -> str | None:
    if not text:
        return None
    match = re.search(r'(?<![a-zA-Z])(RJ|rj)\d{6,8}', text)
    if match:
        return match.group(0).upper()
    return None

IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp"}

DLsite_WORK_CATEGORIES = ("doujin", "books", "pro", "maniax", "girls", "bl", "trans", "serial")
DLsite_IMAGE_EXTENSIONS = ("jpg", "webp")


def safe_project_name(file_name: str) -> str:
    # 1. First check if file_name contains RJ code (highly preferred for background threads)
    rj = extract_rj_code(file_name)
    if rj:
        return rj

    # 2. Check if user manually entered rj_code in session state (catch BaseException for thread safety)
    try:
        import streamlit as st
        if "rj_code" in st.session_state and st.session_state.rj_code.strip():
            rj = extract_rj_code(st.session_state.rj_code)
            if rj:
                return rj
    except BaseException:
        pass

    # 3. Check if script content or metadata has RJ code
    try:
        import streamlit as st
        if "original_script" in st.session_state and st.session_state.original_script:
            rj = extract_rj_code(st.session_state.original_script)
            if rj:
                return rj
        if "metadata_text" in st.session_state and st.session_state.metadata_text:
            rj = extract_rj_code(st.session_state.metadata_text)
            if rj:
                return rj
    except BaseException:
        pass

    # 4. Fallback to filename sanitization
    base_name, _ = os.path.splitext(file_name or "script.txt")
    return re.sub(r"[^a-zA-Z0-9_\-]", "_", base_name)


def get_backup_dir(file_name: str, create: bool = False) -> str:
    proj_name = safe_project_name(file_name)
    project_dir = os.path.join(BACKUP_ROOT, proj_name)
    if create:
        os.makedirs(project_dir, exist_ok=True)
    
    # 마이그레이션 로직: 기존에 DLdata/RJXXXXXX 내부에 저장되어 있던 메타데이터가 있으면 복사해 옵니다.
    old_dir = os.path.join(os.path.abspath("./DLdata"), proj_name)
    if create and os.path.exists(old_dir) and os.path.abspath(old_dir) != os.path.abspath(project_dir):
        import shutil
        # 주요 프로젝트 설정 복사
        for f in ["progress.json", "persona.json", "chats.json", "thumbnail.jpg", "thumbnail.png", "thumbnail.webp", "scenario.txt"]:
            old_file = os.path.join(old_dir, f)
            new_file = os.path.join(project_dir, f)
            if os.path.exists(old_file) and not os.path.exists(new_file):
                try:
                    if f == "scenario.txt":
                        from core.utils import decode_text
                        with open(old_file, "rb") as sf:
                            raw_data = sf.read()
                        decoded_text = decode_text(raw_data)
                        with open(new_file, "w", encoding="utf-8") as df:
                            df.write(decoded_text)
                    else:
                        shutil.copy(old_file, new_file)
                except Exception:
                    try:
                        shutil.copy(old_file, new_file)
                    except Exception:
                        pass
        # 이미지 폴더 통째로 복사
        old_images = os.path.join(old_dir, "images")
        new_images = os.path.join(project_dir, "images")
        if os.path.exists(old_images) and not os.path.exists(new_images):
            try:
                shutil.copytree(old_images, new_images)
            except Exception:
                pass
    return project_dir


def _dlsite_folder_codes(rj_num: int, padding: int) -> list[str]:
    folder_nums = [
        ((rj_num + 999) // 1000) * 1000,
        (rj_num // 1000) * 1000,
    ]

    folder_codes = []
    seen = set()
    for folder_num in folder_nums:
        if folder_num <= 0:
            continue
        folder_code = f"RJ{folder_num:0{padding}d}"
        if folder_code not in seen:
            seen.add(folder_code)
            folder_codes.append(folder_code)
    return folder_codes


def _dlsite_thumbnail_urls(rj_code: str) -> list[str]:
    match = re.search(r"RJ(\d+)", rj_code, re.IGNORECASE)
    if not match:
        return []

    rj_num_str = match.group(1)
    normalized_rj = f"RJ{rj_num_str}"
    rj_num = int(rj_num_str)
    folder_codes = _dlsite_folder_codes(rj_num, len(rj_num_str))

    urls = []
    seen = set()

    def add_url(url: str) -> None:
        if url not in seen:
            seen.add(url)
            urls.append(url)

    for category in DLsite_WORK_CATEGORIES:
        for folder_code in folder_codes:
            for ext in DLsite_IMAGE_EXTENSIONS:
                add_url(
                    f"https://img.dlsite.jp/modpub/images2/work/{category}/{folder_code}/{normalized_rj}_img_main.{ext}"
                )

    prefix = normalized_rj[:5]
    for ext in DLsite_IMAGE_EXTENSIONS:
        add_url(f"https://img.dlsite.jp/modpub/images2/work/serial/{prefix}/{normalized_rj}_img_main.{ext}")

    return urls


def download_dlsite_thumbnail(rj_code: str, target_dir: str) -> str | None:
    """
    DLsite에서 주어진 RJ 코드에 해당하는 썸네일을 다운로드하여 target_dir에 저장합니다.
    """
    urls = _dlsite_thumbnail_urls(rj_code)
    
    # Extract RJ digits for api.asmr-200.com fallback
    match = re.search(r"RJ(\d+)", rj_code, re.IGNORECASE)
    if not match:
        match = re.search(r"(\d+)", rj_code)
    if match:
        rj_num = match.group(1)
        urls.append(f"https://api.asmr-200.com/api/cover/{rj_num}.jpg?type=main")

    if not urls:
        return None

    import requests
    from urllib.parse import urlparse
    headers = {"User-Agent": "Mozilla/5.0"}

    os.makedirs(target_dir, exist_ok=True)
    for url in urls:
        try:
            res = requests.get(url, timeout=5, headers=headers)
            content_type = res.headers.get("Content-Type", "")
            if res.status_code != 200 or not content_type.lower().startswith("image/"):
                continue

            parsed_path = urlparse(url).path
            ext = os.path.splitext(parsed_path)[1].lower()
            target_path = os.path.join(target_dir, f"thumbnail{ext}")
            with open(target_path, "wb") as f:
                f.write(res.content)
            return target_path
        except Exception:
            pass
            
    return None


def get_backup_path(file_name: str) -> str:
    return os.path.join(get_backup_dir(file_name), "progress.json")


def get_writable_backup_path(file_name: str) -> str:
    return os.path.join(get_backup_dir(file_name, create=True), "progress.json")


def save_progress(file_name: str, original_chunks: list[str], translated_chunks: list[str], original_script: str = None) -> str:
    backup_path = get_writable_backup_path(file_name)
    data = {
        "file_name": file_name,
        "original_chunks": original_chunks,
        "translated_chunks": translated_chunks,
    }
    with open(backup_path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
        
    # 원본 대본 전체를 scenario.txt로 함께 자동 저장하여 원클릭 복원에 사용합니다.
    if not original_script:
        try:
            import streamlit as st
            # StopException은 BaseException을 상속받으므로 안전하게 캐칭
            if "original_script" in st.session_state:
                original_script = st.session_state.original_script
        except BaseException:
            original_script = None

    if original_script:
        try:
            proj_dir = get_backup_dir(file_name, create=True)
            scenario_path = os.path.join(proj_dir, "scenario.txt")
            with open(scenario_path, "w", encoding="utf-8") as sf:
                sf.write(original_script)
        except BaseException:
            pass
        
    return backup_path


def load_progress(file_name: str) -> dict | None:
    backup_path = get_backup_path(file_name)
    if not os.path.exists(backup_path):
        return None

    with open(backup_path, "r", encoding="utf-8") as f:
        return json.load(f)


def list_saved_images(file_name: str) -> list[str]:
    images_dir = os.path.join(get_backup_dir(file_name), "images")
    if not os.path.exists(images_dir):
        return []

    saved_images = [
        os.path.join(images_dir, name)
        for name in os.listdir(images_dir)
        if not name.startswith(".") and os.path.splitext(name)[1].lower() in IMAGE_EXTENSIONS
    ]
    saved_images.sort()
    return saved_images


def get_image_note_path(image_path: str) -> str:
    base_path, _ = os.path.splitext(image_path)
    return f"{base_path}.analysis.txt"


def load_image_note(image_path: str) -> str | None:
    note_path = get_image_note_path(image_path)
    if not os.path.exists(note_path):
        return None

    with open(note_path, "r", encoding="utf-8") as f:
        return f.read()


def save_image_note(image_path: str, note: str) -> str:
    note_path = get_image_note_path(image_path)
    with open(note_path, "w", encoding="utf-8") as f:
        f.write(note)
    return note_path


def get_summary_dir(file_name: str) -> str:
    summary_dir = os.path.join(get_backup_dir(file_name, create=True), "summaries")
    os.makedirs(summary_dir, exist_ok=True)
    return summary_dir


def get_chunk_summary_path(file_name: str, chunk_idx: int) -> str:
    return os.path.join(get_summary_dir(file_name), f"chunk_{chunk_idx + 1:04d}.summary.json")


def chunk_hash(chunk_text: str) -> str:
    return hashlib.sha256(chunk_text.encode("utf-8")).hexdigest()


def load_chunk_summary(file_name: str, chunk_idx: int, chunk_text: str) -> str | None:
    summary_path = get_chunk_summary_path(file_name, chunk_idx)
    if not os.path.exists(summary_path):
        return None

    with open(summary_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    if data.get("source_hash") != chunk_hash(chunk_text):
        return None

    return data.get("summary")


def save_chunk_summary(file_name: str, chunk_idx: int, chunk_text: str, summary: str) -> str:
    summary_path = get_chunk_summary_path(file_name, chunk_idx)
    data = {
        "chunk_index": chunk_idx,
        "source_hash": chunk_hash(chunk_text),
        "summary": summary,
    }
    with open(summary_path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    return summary_path

def get_persona_backup_path(file_name: str) -> str:
    return os.path.join(get_backup_dir(file_name), "persona.json")


def get_writable_persona_backup_path(file_name: str) -> str:
    return os.path.join(get_backup_dir(file_name, create=True), "persona.json")


def save_persona_backup(file_name: str, persona: dict, glossary: list, script_summary: dict = None):
    path = get_writable_persona_backup_path(file_name)
    existing_data = {}
    if os.path.exists(path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                existing_data = json.load(f)
        except Exception:
            pass
            
    summary_data = script_summary if script_summary is not None else existing_data.get("script_summary", {})
    data = {
        "persona": persona,
        "glossary_data": glossary,
        "script_summary": summary_data
    }
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def load_persona_backup(file_name: str) -> dict | None:
    path = get_persona_backup_path(file_name)
    if os.path.exists(path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return None


def list_saved_personas() -> list[str]:
    if not os.path.exists(BACKUP_ROOT):
        return []
    projects = []
    for d in os.listdir(BACKUP_ROOT):
        dir_path = os.path.join(BACKUP_ROOT, d)
        if os.path.isdir(dir_path):
            if os.path.exists(os.path.join(dir_path, "persona.json")):
                projects.append(d)
    projects.sort()
    return projects


def load_persona_by_project_name(project_name: str) -> dict | None:
    path = os.path.join(BACKUP_ROOT, project_name, "persona.json")
    if os.path.exists(path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return None


MASTER_GLOSSARY_PATH = os.path.abspath("./master_glossary.json")

def load_master_glossary() -> list[dict]:
    if not os.path.exists(MASTER_GLOSSARY_PATH):
        return []
    try:
        with open(MASTER_GLOSSARY_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
            if isinstance(data, list):
                # Ensure all items have the required columns
                normalized = []
                for item in data:
                    src = item.get("원어 (Source)") or item.get("source") or ""
                    tgt = item.get("번역어 (Target)") or item.get("target") or ""
                    ctx = item.get("설명/뉘앙스 (Context)") or item.get("context") or item.get("설명") or ""
                    is_proper = item.get("고유명사 (Proper Noun)", False)
                    if src.strip():
                        normalized.append({
                            "원어 (Source)": src.strip(),
                            "번역어 (Target)": tgt.strip(),
                            "설명/뉘앙스 (Context)": ctx.strip(),
                            "고유명사 (Proper Noun)": bool(is_proper)
                        })
                return normalized
    except Exception:
        pass
    return []

def save_master_glossary(glossary_list: list[dict]):
    normalized = []
    for item in glossary_list:
        src = str(item.get("원어 (Source)", "")).strip()
        tgt = str(item.get("번역어 (Target)", "")).strip()
        ctx = str(item.get("설명/뉘앙스 (Context)", "")).strip()
        is_proper = item.get("고유명사 (Proper Noun)", False)
        if src:
            normalized.append({
                "원어 (Source)": src,
                "번역어 (Target)": tgt,
                "설명/뉘앙스 (Context)": ctx,
                "고유명사 (Proper Noun)": bool(is_proper)
            })
    sorted_list = sorted(normalized, key=lambda x: x["원어 (Source)"].lower())
    with open(MASTER_GLOSSARY_PATH, "w", encoding="utf-8") as f:
        json.dump(sorted_list, f, ensure_ascii=False, indent=2)

def merge_glossaries(master: list[dict], project: list[dict]) -> list[dict]:
    master_dict = {str(item.get("원어 (Source)", "")).strip(): item for item in master if item.get("원어 (Source)")}
    for item in project:
        src = str(item.get("원어 (Source)", "")).strip() or str(item.get("원어 (영문/일문 등)", "")).strip()
        tgt = str(item.get("번역어 (Target)", "")).strip() or str(item.get("고정 번역어 (한글)", "")).strip()
        if not src or not tgt:
            continue
        desc = str(item.get("설명/뉘앙스 (Context)", "")).strip()
        is_proper = item.get("고유명사 (Proper Noun)", False)
        if src in master_dict:
            master_dict[src]["번역어 (Target)"] = tgt
            if desc:
                master_dict[src]["설명/뉘앙스 (Context)"] = desc
            # 만약 프로젝트 단어장에서 명시적으로 고유명사로 체크했거나 기존에 체크되어 있었다면 True 유지
            master_dict[src]["고유명사 (Proper Noun)"] = bool(is_proper or master_dict[src].get("고유명사 (Proper Noun)", False))
        else:
            master_dict[src] = {
                "원어 (Source)": src,
                "번역어 (Target)": tgt,
                "설명/뉘앙스 (Context)": desc,
                "고유명사 (Proper Noun)": bool(is_proper)
            }
    return list(master_dict.values())
