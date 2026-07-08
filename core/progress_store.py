import json
import hashlib
import os
import re


BACKUP_ROOT = os.path.abspath("./DLdata")

def extract_rj_code(text: str) -> str | None:
    if not text:
        return None
    match = re.search(r'\b(RJ|rj)\d{6,8}\b', text)
    if match:
        return match.group(0).upper()
    return None

IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp"}


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


def get_backup_dir(file_name: str) -> str:
    project_dir = os.path.join(BACKUP_ROOT, safe_project_name(file_name))
    os.makedirs(project_dir, exist_ok=True)
    return project_dir


def get_backup_path(file_name: str) -> str:
    return os.path.join(get_backup_dir(file_name), "progress.json")


def save_progress(file_name: str, original_chunks: list[str], translated_chunks: list[str]) -> str:
    backup_path = get_backup_path(file_name)
    data = {
        "file_name": file_name,
        "original_chunks": original_chunks,
        "translated_chunks": translated_chunks,
    }
    with open(backup_path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
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
    summary_dir = os.path.join(get_backup_dir(file_name), "summaries")
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


def save_persona_backup(file_name: str, persona: dict, glossary: list):
    path = get_persona_backup_path(file_name)
    data = {
        "persona": persona,
        "glossary_data": glossary
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
                    if src.strip():
                        normalized.append({
                            "원어 (Source)": src.strip(),
                            "번역어 (Target)": tgt.strip(),
                            "설명/뉘앙스 (Context)": ctx.strip()
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
        if src:
            normalized.append({
                "원어 (Source)": src,
                "번역어 (Target)": tgt,
                "설명/뉘앙스 (Context)": ctx
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
        if src in master_dict:
            master_dict[src]["번역어 (Target)"] = tgt
            if desc:
                master_dict[src]["설명/뉘앙스 (Context)"] = desc
        else:
            master_dict[src] = {
                "원어 (Source)": src,
                "번역어 (Target)": tgt,
                "설명/뉘앙스 (Context)": desc
            }
    return list(master_dict.values())
