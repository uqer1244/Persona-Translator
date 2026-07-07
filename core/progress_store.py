import json
import hashlib
import os
import re


BACKUP_ROOT = os.path.abspath("./temp_backups")
IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp"}


def safe_project_name(file_name: str) -> str:
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
