import json
import os

from core.document import chunk_text
from core.progress_store import BACKUP_ROOT, get_backup_dir


def get_bot_card_dir(file_name: str) -> str:
    path = os.path.join(get_backup_dir(file_name, create=True), "bot_card")
    os.makedirs(path, exist_ok=True)
    return path


def get_bot_card_cache_dir(file_name: str) -> str:
    path = os.path.join(get_bot_card_dir(file_name), "chunks")
    os.makedirs(path, exist_ok=True)
    return path


def get_bot_card_path(file_name: str) -> str:
    return os.path.join(get_bot_card_dir(file_name), "bot_card.json")


def load_bot_card(file_name: str) -> dict | None:
    path = get_bot_card_path(file_name)
    if not os.path.exists(path):
        return None
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def save_bot_card(file_name: str, card: dict) -> str:
    path = get_bot_card_path(file_name)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(card, f, ensure_ascii=False, indent=2)
    return path


def save_project_bot_card(project_name: str, card: dict) -> str:
    path = os.path.join(BACKUP_ROOT, project_name, "bot_card.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(card, f, ensure_ascii=False, indent=2)
    return path


def load_project_bot_card(project_name: str) -> dict | None:
    path = os.path.join(BACKUP_ROOT, project_name, "bot_card.json")
    if not os.path.exists(path):
        return None
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def load_progress_for_project(project_name: str) -> dict | None:
    path = os.path.join(BACKUP_ROOT, project_name, "progress.json")
    if not os.path.exists(path):
        return None
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def load_persona_for_project(project_name: str) -> dict:
    path = os.path.join(BACKUP_ROOT, project_name, "persona.json")
    if not os.path.exists(path):
        return {}
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def load_script_chunks_for_project(project_name: str) -> tuple[str, list[str], list[str]]:
    progress = load_progress_for_project(project_name)
    if not progress:
        return "script.txt", [], []
    file_name = progress.get("file_name", f"{project_name}.txt")
    originals = progress.get("original_chunks", []) or []
    translated = progress.get("translated_chunks", []) or []
    return file_name, originals, translated


def load_scenario_chunks(project_name: str, chunk_size: int = 1800) -> list[str]:
    scenario_path = os.path.join(BACKUP_ROOT, project_name, "scenario.txt")
    if not os.path.exists(scenario_path):
        return []
    with open(scenario_path, "r", encoding="utf-8") as f:
        return chunk_text(f.read(), chunk_size=chunk_size)


def select_source_chunks(
    original_chunks: list[str],
    translated_chunks: list[str],
    prefer_translated: bool,
) -> list[str]:
    if prefer_translated and translated_chunks and any(c.strip() for c in translated_chunks):
        merged = []
        for idx, original in enumerate(original_chunks):
            translated = translated_chunks[idx] if idx < len(translated_chunks) else ""
            merged.append(translated if translated.strip() else original)
        return merged
    return original_chunks
