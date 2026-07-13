import hashlib
import json
import os

from core.analyzer import _generate_text, _json_correction_rules, _json_rules, _parse_json_response
from core.bot_card_prompts import (
    build_card_synthesis_prompt,
    fallback_card_fields,
)
from core.bot_card_storage import (
    load_persona_for_project,
    load_scenario_chunks,
    load_script_chunks_for_project,
    save_bot_card,
    save_project_bot_card,
    select_source_chunks,
)
from core.risu_card import export_charx_bytes, make_risu_card


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


def build_bot_card_from_map(
    model,
    processor,
    project_name: str,
    file_name: str,
    event_map: dict,
    persona_data: dict | None = None,
    metadata_text: str = "",
    card_name: str = "",
) -> dict:
    persona_data = persona_data or {}
    prompt = build_card_synthesis_prompt(
        json_rules=_json_rules(model, processor),
        event_map=event_map,
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
    
    # Rebuild script text from small chunks
    script_text = ""
    if source_chunks:
        script_text = "\n".join(source_chunks)
    else:
        # Fallback to scenario
        scenario_chunks = load_scenario_chunks(project_name)
        script_text = "\n".join(scenario_chunks)

    if not script_text.strip():
        raise ValueError("대본 스크립트를 찾을 수 없습니다. 먼저 대본을 프로젝트로 저장해 주세요.")

    from core.document import chunk_text
    from core.event_mapper import MAP_CHUNK_SIZE, summarize_chunk, extract_event_map

    # Re-slice into large chunks (3500 chars) for Map stage
    large_chunks = chunk_text(script_text, chunk_size=MAP_CHUNK_SIZE)
    if not large_chunks:
        raise ValueError("대본 청크 분할에 실패했습니다.")

    if max_chunks:
        large_chunks = large_chunks[:max_chunks]

    # Stage 1: Map (Chunk-wise summarization)
    chunk_summaries = []
    total_large = len(large_chunks)
    for idx, chunk in enumerate(large_chunks):
        if progress_callback:
            progress_callback(idx, total_large, "chunk")
        summary = summarize_chunk(
            model=model,
            processor=processor,
            file_name=file_name,
            chunk_text=chunk,
            chunk_index=idx,
            total_chunks=total_large,
        )
        chunk_summaries.append(summary)

    # Stage 2: Reduce (Global Event & Causal Map extraction)
    if progress_callback:
        progress_callback(total_large, total_large, "synthesis")

    event_map = extract_event_map(
        model=model,
        processor=processor,
        file_name=file_name,
        chunk_summaries=chunk_summaries,
        metadata_text=metadata_text,
    )

    # Stage 3: Synthesis (Final Bot Card generation)
    card = build_bot_card_from_map(
        model=model,
        processor=processor,
        project_name=project_name,
        file_name=file_name,
        event_map=event_map,
        persona_data=load_persona_for_project(project_name),
        metadata_text=metadata_text,
        card_name=card_name,
    )
    
    save_bot_card(file_name, card)
    save_project_bot_card(project_name, card)
    return card
