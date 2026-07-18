import hashlib
import json
import os
import re

from core.model_generation import (
    generate_text as _generate_text,
    json_correction_rules as _json_correction_rules,
    json_rules as _json_rules,
)
from core.json_repair import parse_json_response as _parse_json_response
from core.model_manager import clear_mlx_cache as _clear_mlx_cache
from core.document import chunk_text
from core.bot_card_storage import get_bot_card_dir

EVENT_MAPPER_CACHE_VERSION = 4
MAP_CHUNK_SIZE = 3500


def get_chunk_summaries_dir(file_name: str) -> str:
    path = os.path.join(get_bot_card_dir(file_name), "chunk_summaries")
    os.makedirs(path, exist_ok=True)
    return path


def _chunk_source_hash(chunk_text: str) -> str:
    return hashlib.sha256(chunk_text.encode("utf-8")).hexdigest()


def _safe_parse_chunk_json(model, processor, response: str, default_summary: str) -> dict:
    try:
        return _parse_json_response(response)
    except Exception:
        correction_prompt = f"""{_json_correction_rules(model, processor)}

[오류 결과물]
{response}

[반드시 JSON 객체만 출력]"""
        try:
            corrected = _generate_text(model, processor, correction_prompt, max_tokens=600, temp=0.1, force_json=True).strip()
            return _parse_json_response(corrected)
        except Exception:
            summary_match = re.search(r'"summary"\s*:\s*"([^"]+)"', response)
            image_prompt_match = re.search(r'"image_prompt"\s*:\s*"([^"]+)"', response)
            
            summary = summary_match.group(1) if summary_match else default_summary
            image_prompt = image_prompt_match.group(1) if image_prompt_match else ""
            
            if not summary_match:
                cleaned = re.sub(r'[{}]', '', response).strip()
                summary = cleaned
            
            return {
                "summary": summary,
                "image_prompt": image_prompt
            }


def summarize_chunk(
    model,
    processor,
    file_name: str,
    chunk_text: str,
    chunk_index: int,
    total_chunks: int,
) -> str:
    """
    각 청크의 핵심 대사와 인물 간 교류, 분위기를 150-250자의 텍스트 요약으로 압축하고,
    anima 이미지 생성 모델용 영문 프롬프트도 함께 추출합니다.
    """
    from core.bot_card_prompts import build_chunk_compression_prompt

    cache_dir = get_chunk_summaries_dir(file_name)
    cache_path = os.path.join(cache_dir, f"summary_{chunk_index + 1:04d}.json")
    source_hash = _chunk_source_hash(chunk_text)

    # Try to load cached summary
    if os.path.exists(cache_path):
        try:
            with open(cache_path, "r", encoding="utf-8") as f:
                cached = json.load(f)
            if (
                cached.get("cache_version") == EVENT_MAPPER_CACHE_VERSION
                and cached.get("source_hash") == source_hash
                and "image_prompt" in cached
            ):
                return cached.get("summary", "")
        except Exception:
            pass

    prompt = build_chunk_compression_prompt(
        json_rules=_json_rules(model, processor),
        chunk_text=chunk_text,
        chunk_index=chunk_index,
        total_chunks=total_chunks,
    )

    try:
        response = _generate_text(model, processor, prompt, max_tokens=1000, temp=0.1, force_json=True).strip()
        parsed = _safe_parse_chunk_json(model, processor, response, default_summary="")
        summary = parsed.get("summary", "").strip()
        image_prompt = parsed.get("image_prompt", "").strip()
        
        if not summary:
            summary = response
    except Exception as e:
        summary = f"[Error summarizing chunk {chunk_index + 1}: {e}]"
        image_prompt = ""
    finally:
        _clear_mlx_cache()

    # Save to cache
    try:
        with open(cache_path, "w", encoding="utf-8") as f:
            json.dump(
                {
                    "cache_version": EVENT_MAPPER_CACHE_VERSION,
                    "chunk_index": chunk_index,
                    "source_hash": source_hash,
                    "summary": summary,
                    "image_prompt": image_prompt,
                },
                f,
                ensure_ascii=False,
                indent=2,
            )
    except Exception:
        pass

    return summary


def extract_event_map(
    model,
    processor,
    file_name: str,
    chunk_summaries: list[str],
    metadata_text: str = "",
) -> dict:
    """
    시간순으로 종합된 요약 시퀀스로부터 전체 대본의 서사적 사건 지도 및 인과관계를 추출합니다.
    """
    from core.bot_card_prompts import build_event_map_prompt

    joined_summaries = ""
    for idx, summary in enumerate(chunk_summaries):
        joined_summaries += f"[구간 {idx + 1} 요약]\n{summary}\n\n"

    json_rules = _json_rules(model, processor)
    prompt = build_event_map_prompt(
        json_rules=json_rules,
        joined_summaries=joined_summaries,
        metadata_text=metadata_text,
    )

    fallback = {
        "narrative_progression": [],
        "global_relationship_arc": "",
    }

    try:
        response = _generate_text(model, processor, prompt, max_tokens=2200, temp=0.15, force_json=True)
        try:
            return _parse_json_response(response)
        except Exception:
            # Correction attempt
            correction_prompt = f"""{_json_correction_rules(model, processor)}

[오류 결과물]
{response}

[반드시 JSON 객체만 출력]"""
            try:
                corrected = _generate_text(model, processor, correction_prompt, max_tokens=1400, temp=0.1, force_json=True)
                return _parse_json_response(corrected)
            except Exception:
                return fallback
    finally:
        _clear_mlx_cache()
