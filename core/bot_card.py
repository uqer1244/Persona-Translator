import hashlib
import json
import os

from core.analyzer import _generate_text, _json_correction_rules, _json_rules, _parse_json_response
from core.bot_card_prompts import (
    build_card_synthesis_prompt,
    build_chunk_analysis_prompt,
    fallback_card_fields,
)
from core.bot_card_storage import (
    get_bot_card_cache_dir,
    load_bot_card,
    load_persona_for_project,
    load_scenario_chunks,
    load_script_chunks_for_project,
    save_bot_card,
    save_project_bot_card,
    select_source_chunks,
)
from core.risu_card import export_charx_bytes, make_risu_card


BOT_CARD_CHUNK_CACHE_VERSION = 2


def _chunk_source_hash(chunk_text: str) -> str:
    return hashlib.sha256(chunk_text.encode("utf-8")).hexdigest()


def _safe_parse_json(model, processor, response: str, fallback: dict) -> dict:
    try:
        return _parse_json_response(response)
    except Exception:
        correction_prompt = f"""{_json_correction_rules(model, processor)}

[오류 결과물]
{response}

[반드시 JSON 객체만 출력]"""
        try:
            corrected = _generate_text(model, processor, correction_prompt, max_tokens=1400, temp=0.1, force_json=True)
            return _parse_json_response(corrected)
        except Exception:
            return fallback


def analyze_bot_card_chunk(
    model,
    processor,
    file_name: str,
    chunk_text: str,
    chunk_index: int,
    total_chunks: int,
    metadata_text: str = "",
) -> dict:
    cache_dir = get_bot_card_cache_dir(file_name)
    cache_path = os.path.join(cache_dir, f"chunk_{chunk_index + 1:04d}.json")
    source_hash = _chunk_source_hash(chunk_text)

    cached = _load_cached_chunk_analysis(cache_path, source_hash)
    if cached is not None:
        return cached

    prompt = build_chunk_analysis_prompt(
        json_rules=_json_rules(model, processor),
        chunk_text=chunk_text,
        chunk_index=chunk_index,
        total_chunks=total_chunks,
        metadata_text=metadata_text,
    )
    fallback = _fallback_chunk_analysis(chunk_text)
    response = _generate_text(model, processor, prompt, max_tokens=1800, temp=0.15, force_json=True)
    analysis = _safe_parse_json(model, processor, response, fallback)
    _save_chunk_analysis(cache_path, chunk_index, source_hash, analysis)
    return analysis


def _load_cached_chunk_analysis(cache_path: str, source_hash: str) -> dict | None:
    if not os.path.exists(cache_path):
        return None
    try:
        with open(cache_path, "r", encoding="utf-8") as f:
            cached = json.load(f)
        if cached.get("source_hash") == source_hash and cached.get("cache_version") == BOT_CARD_CHUNK_CACHE_VERSION:
            return cached.get("analysis", {})
    except Exception:
        return None
    return None


def _save_chunk_analysis(cache_path: str, chunk_index: int, source_hash: str, analysis: dict) -> None:
    with open(cache_path, "w", encoding="utf-8") as f:
        json.dump(
            {
                "cache_version": BOT_CARD_CHUNK_CACHE_VERSION,
                "chunk_index": chunk_index,
                "source_hash": source_hash,
                "analysis": analysis,
            },
            f,
            ensure_ascii=False,
            indent=2,
        )


def _fallback_chunk_analysis(chunk_text: str) -> dict:
    return {
        "scene_summary": chunk_text[:300],
        "scenario_facts": [],
        "event_beats": [],
        "character_traits": [],
        "speech_style": [],
        "first_message_candidates": [],
        "dialogue_examples": [],
        "lore_candidates": [],
        "relationship_notes": [],
        "recallable_memories": [],
        "safety_notes": [],
    }


def build_bot_card_from_analyses(
    model,
    processor,
    project_name: str,
    file_name: str,
    analyses: list[dict],
    persona_data: dict | None = None,
    metadata_text: str = "",
    card_name: str = "",
) -> dict:
    persona_data = persona_data or {}
    prompt = build_card_synthesis_prompt(
        json_rules=_json_rules(model, processor),
        analyses=analyses,
        persona_data=persona_data,
        metadata_text=metadata_text,
    )
    fallback_name = card_name or project_name or os.path.splitext(file_name)[0]
    fallback = fallback_card_fields(project_name, file_name, persona_data, card_name)

    response = _generate_text(model, processor, prompt, max_tokens=3500, temp=0.2, force_json=True)
    card_fields = _safe_parse_json(model, processor, response, fallback)
    return make_risu_card(card_fields, fallback_name)


def generate_bot_card(
    model,
    processor,
    project_name: str,
    metadata_text: str = "",
    prefer_translated: bool = True,
    max_chunks: int | None = None,
    card_name: str = "",
    progress_callback=None,
) -> dict:
    file_name, original_chunks, translated_chunks = load_script_chunks_for_project(project_name)
    source_chunks = select_source_chunks(original_chunks, translated_chunks, prefer_translated)
    if not source_chunks:
        source_chunks = load_scenario_chunks(project_name)
    if max_chunks:
        source_chunks = source_chunks[:max_chunks]
    if not source_chunks:
        raise ValueError("대본 청크를 찾을 수 없습니다. 먼저 대본을 프로젝트로 저장해 주세요.")

    analyses = analyze_all_chunks(
        model,
        processor,
        file_name=file_name,
        source_chunks=source_chunks,
        metadata_text=metadata_text,
        progress_callback=progress_callback,
    )
    if progress_callback:
        progress_callback(len(source_chunks), len(source_chunks), "synthesis")

    card = build_bot_card_from_analyses(
        model,
        processor,
        project_name=project_name,
        file_name=file_name,
        analyses=analyses,
        persona_data=load_persona_for_project(project_name),
        metadata_text=metadata_text,
        card_name=card_name,
    )
    save_bot_card(file_name, card)
    save_project_bot_card(project_name, card)
    return card


def analyze_all_chunks(
    model,
    processor,
    file_name: str,
    source_chunks: list[str],
    metadata_text: str = "",
    progress_callback=None,
) -> list[dict]:
    analyses = []
    total = len(source_chunks)
    for idx, chunk in enumerate(source_chunks):
        if progress_callback:
            progress_callback(idx, total, "chunk")
        analyses.append(
            analyze_bot_card_chunk(
                model,
                processor,
                file_name=file_name,
                chunk_text=chunk,
                chunk_index=idx,
                total_chunks=total,
                metadata_text=metadata_text,
            )
        )
    return analyses
