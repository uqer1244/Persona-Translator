import json
import hashlib
import os
import re
import datetime

BACKUP_ROOT = os.path.abspath("./projects")
MASTER_GLOSSARY_PATH = os.path.abspath("./master_glossary.json")

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
    # 1. First check if file_name contains RJ code
    rj = extract_rj_code(file_name)
    if rj:
        return rj

    # 2. Check if user manually entered rj_code in session state
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
    
    # Legacy migration copy logic (directory backup fallback)
    old_dir = os.path.join(os.path.abspath("./DLdata"), proj_name)
    if create and os.path.exists(old_dir) and os.path.abspath(old_dir) != os.path.abspath(project_dir):
        import shutil
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
    urls = _dlsite_thumbnail_urls(rj_code)
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


# --- SQLite DB Delegated Operations ---

def save_progress(file_name: str, original_chunks: list[str], translated_chunks: list[str], original_script: str = None) -> str:
    from core.database import db
    project_name = safe_project_name(file_name)
    
    if not original_script:
        try:
            import streamlit as st
            if "original_script" in st.session_state:
                original_script = st.session_state.original_script
        except BaseException:
            pass
    if not original_script:
        original_script = "\n".join(original_chunks)
        
    translated_script = "\n".join([c for c in translated_chunks if c])
    rj_code = extract_rj_code(project_name) or extract_rj_code(file_name) or extract_rj_code(original_script) or ""
    now = datetime.datetime.now().isoformat()
    
    # Save project to projects table
    exists = db.run_query("SELECT 1 FROM projects WHERE project_name = ?", (project_name,), fetch_one=True)
    if not exists:
        db.run_query(
            """
            INSERT INTO projects (
                project_name, rj_code, file_name, metadata_text, 
                original_script, translated_script, tone, relationship, 
                situation, key_rules, script_summary, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (project_name, rj_code, file_name, "", original_script, translated_script, "", "", "", "[]", "{}", now, now),
            commit=True
        )
    else:
        db.run_query(
            """
            UPDATE projects 
            SET file_name = ?, rj_code = ?, original_script = ?, translated_script = ?, updated_at = ?
            WHERE project_name = ?
            """,
            (file_name, rj_code, original_script, translated_script, now, project_name),
            commit=True
        )
        
    # Re-save chunks
    db.run_query("DELETE FROM chunks WHERE project_name = ?", (project_name,), commit=True)
    for idx, (orig, trans) in enumerate(zip(original_chunks, translated_chunks)):
        db.run_query(
            """
            INSERT INTO chunks (project_name, chunk_index, original_text, translated_text, status)
            VALUES (?, ?, ?, ?, ?)
            """,
            (project_name, idx, orig, trans, 'completed' if trans.strip() else 'pending'),
            commit=True
        )
    
    # Create directories for thumbnails/images
    get_backup_dir(file_name, create=True)
    
    if original_script:
        try:
            proj_dir = get_backup_dir(file_name, create=True)
            scenario_path = os.path.join(proj_dir, "scenario.txt")
            with open(scenario_path, "w", encoding="utf-8") as sf:
                sf.write(original_script)
        except BaseException:
            pass
        
    return os.path.join(get_backup_dir(file_name), "progress.json")


def load_progress(file_name: str) -> dict | None:
    from core.database import db
    project_name = safe_project_name(file_name)
    
    proj = db.run_query("SELECT file_name FROM projects WHERE project_name = ?", (project_name,), fetch_one=True)
    if not proj:
        return None
        
    chunks = db.run_query(
        "SELECT original_text, translated_text FROM chunks WHERE project_name = ? ORDER BY chunk_index ASC", 
        (project_name,), 
        fetch_all=True
    )
    
    return {
        "file_name": proj["file_name"],
        "original_chunks": [c["original_text"] for c in chunks],
        "translated_chunks": [c["translated_text"] for c in chunks]
    }


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
    from core.database import db
    row = db.run_query("SELECT analysis_note FROM image_notes WHERE image_path = ?", (image_path,), fetch_one=True)
    if row:
        return row["analysis_note"]
    
    # Fallback note file
    note_path = get_image_note_path(image_path)
    if os.path.exists(note_path):
        try:
            with open(note_path, "r", encoding="utf-8") as f:
                return f.read()
        except Exception:
            pass
    return None


def save_image_note(image_path: str, note: str) -> str:
    from core.database import db
    project_name = "unknown"
    parts = os.path.normpath(image_path).split(os.sep)
    try:
        idx = parts.index("projects")
        if idx + 1 < len(parts):
            project_name = parts[idx + 1]
    except ValueError:
        pass
        
    db.run_query(
        "INSERT OR REPLACE INTO image_notes (project_name, image_path, analysis_note) VALUES (?, ?, ?)",
        (project_name, image_path, note),
        commit=True
    )
    
    note_path = get_image_note_path(image_path)
    try:
        with open(note_path, "w", encoding="utf-8") as f:
            f.write(note)
    except Exception:
        pass
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
    from core.database import db
    project_name = safe_project_name(file_name)
    
    exists = db.run_query(
        "SELECT script_summary FROM projects WHERE project_name = ?", 
        (project_name,), 
        fetch_one=True
    )
    now = datetime.datetime.now().isoformat()
    
    existing_summary = "{}"
    if exists:
        existing_summary = exists["script_summary"] or "{}"
    
    summary_data = script_summary if script_summary is not None else json.loads(existing_summary)
    
    if not exists:
        db.run_query(
            """
            INSERT INTO projects (
                project_name, rj_code, file_name, metadata_text, 
                original_script, translated_script, tone, relationship, 
                situation, key_rules, script_summary, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                project_name, "", file_name, "", "", "", 
                persona.get("tone", ""), persona.get("relationship", ""), persona.get("situation", ""), 
                json.dumps(persona.get("key_rules", [])), json.dumps(summary_data), now, now
            ),
            commit=True
        )
    else:
        db.run_query(
            """
            UPDATE projects
            SET tone = ?, relationship = ?, situation = ?, key_rules = ?, script_summary = ?, updated_at = ?
            WHERE project_name = ?
            """,
            (
                persona.get("tone", ""), persona.get("relationship", ""), persona.get("situation", ""), 
                json.dumps(persona.get("key_rules", [])), json.dumps(summary_data), now, project_name
            ),
            commit=True
        )
        
    # Re-save glossary
    db.run_query("DELETE FROM glossary WHERE project_name = ?", (project_name,), commit=True)
    for item in glossary:
        src = (item.get("원어 (Source)") or item.get("source") or "").strip()
        tgt = (item.get("번역어 (Target)") or item.get("target") or "").strip()
        ctx = (item.get("설명/뉘앙스 (Context)") or item.get("context") or item.get("설명") or "").strip()
        is_proper = 1 if item.get("고유명사 (Proper Noun)", False) else 0
        if src:
            db.run_query(
                """
                INSERT INTO glossary (project_name, source, target, context, is_proper_noun)
                VALUES (?, ?, ?, ?, ?)
                """,
                (project_name, src, tgt, ctx, is_proper),
                commit=True
            )


def load_persona_backup(file_name: str) -> dict | None:
    from core.database import db
    project_name = safe_project_name(file_name)
    
    proj = db.run_query(
        "SELECT tone, relationship, situation, key_rules, script_summary FROM projects WHERE project_name = ?", 
        (project_name,), 
        fetch_one=True
    )
    if not proj:
        return None
        
    glossary_rows = db.run_query(
        "SELECT source, target, context, is_proper_noun FROM glossary WHERE project_name = ?",
        (project_name,),
        fetch_all=True
    )
    
    glossary_data = []
    for g in glossary_rows:
        glossary_data.append({
            "원어 (Source)": g["source"],
            "번역어 (Target)": g["target"],
            "설명/뉘앙스 (Context)": g["context"],
            "고유명사 (Proper Noun)": bool(g["is_proper_noun"])
        })
        
    try:
        key_rules = json.loads(proj["key_rules"] or "[]")
    except Exception:
        key_rules = []
        
    try:
        summary_data = json.loads(proj["script_summary"] or "{}")
    except Exception:
        summary_data = {}
        
    return {
        "persona": {
            "tone": proj["tone"] or "",
            "relationship": proj["relationship"] or "",
            "situation": proj["situation"] or "",
            "key_rules": key_rules
        },
        "glossary_data": glossary_data,
        "script_summary": summary_data
    }


def list_saved_personas() -> list[str]:
    from core.database import db
    rows = db.run_query("SELECT project_name FROM projects ORDER BY project_name ASC", fetch_all=True)
    return [r["project_name"] for r in rows]


def load_persona_by_project_name(project_name: str) -> dict | None:
    return load_persona_backup(project_name)


def load_master_glossary() -> list[dict]:
    from core.database import db
    rows = db.run_query("SELECT source, target, context, is_proper_noun FROM glossary WHERE project_name IS NULL ORDER BY source ASC", fetch_all=True)
    glossary_data = []
    for g in rows:
        glossary_data.append({
            "원어 (Source)": g["source"],
            "번역어 (Target)": g["target"],
            "설명/뉘앙스 (Context)": g["context"],
            "고유명사 (Proper Noun)": bool(g["is_proper_noun"])
        })
    return glossary_data


def save_master_glossary(glossary_list: list[dict]):
    from core.database import db
    db.run_query("DELETE FROM glossary WHERE project_name IS NULL", commit=True)
    for item in glossary_list:
        src = str(item.get("원어 (Source)", "")).strip()
        tgt = str(item.get("번역어 (Target)", "")).strip()
        ctx = str(item.get("설명/뉘앙스 (Context)", "")).strip()
        is_proper = 1 if item.get("고유명사 (Proper Noun)", False) else 0
        if src:
            db.run_query(
                "INSERT INTO glossary (project_name, source, target, context, is_proper_noun) VALUES (NULL, ?, ?, ?, ?)",
                (src, tgt, ctx, is_proper),
                commit=True
            )
            
    # Write back to JSON file too for backwards compatibility
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
    try:
        with open(MASTER_GLOSSARY_PATH, "w", encoding="utf-8") as f:
            json.dump(sorted_list, f, ensure_ascii=False, indent=2)
    except Exception:
        pass


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
            master_dict[src]["고유명사 (Proper Noun)"] = bool(is_proper or master_dict[src].get("고유명사 (Proper Noun)", False))
        else:
            master_dict[src] = {
                "원어 (Source)": src,
                "번역어 (Target)": tgt,
                "설명/뉘앙스 (Context)": desc,
                "고유명사 (Proper Noun)": bool(is_proper)
            }
    return list(master_dict.values())


# Automatically trigger database migration when progress_store is imported
try:
    from core.database import db
except Exception as e:
    print(f"[DATABASE] Database import failed: {e}")
