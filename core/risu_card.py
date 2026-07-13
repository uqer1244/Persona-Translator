import copy
import io
import json
import re
import time
import zipfile


DEFAULT_CARD = {
    "spec": "chara_card_v3",
    "spec_version": "3.0",
    "data": {
        "name": "",
        "description": "",
        "personality": "",
        "scenario": "",
        "first_mes": "",
        "mes_example": "",
        "creator_notes": "",
        "system_prompt": "",
        "post_history_instructions": "",
        "alternate_greetings": [""],
        "character_book": {
            "scan_depth": 5,
            "token_budget": 80000,
            "recursive_scanning": False,
            "extensions": {"risu_fullWordMatching": False},
            "entries": [],
        },
        "tags": ["ASMR", "doujin voice"],
        "creator": "PersonaASMR Studio",
        "character_version": "1.0",
        "extensions": {
            "risuai": {
                "bias": [],
                "viewScreen": "none",
                "utilityBot": False,
                "sdData": [],
                "backgroundHTML": "",
                "additionalText": "",
                "virtualscript": "",
                "largePortrait": False,
                "lorePlus": False,
                "newGenData": {
                    "prompt": "",
                    "negative": "",
                    "instructions": "",
                    "emotionInstructions": "",
                },
                "vits": {},
                "lowLevelAccess": False,
                "defaultVariables": "",
                "prebuiltAssetCommand": "",
                "prebuiltAssetExclude": [],
                "prebuiltAssetStyle": "",
            },
            "depth_prompt": {"depth": 0, "prompt": ""},
        },
        "group_only_greetings": [],
        "nickname": "",
        "source": [],
        "creation_date": int(time.time() * 1000),
        "modification_date": int(time.time()),
        "assets": [],
    },
}


def normalise_dialogue_marks(text: str) -> str:
    if not text:
        return ""
    text = re.sub(r"\[([^\]\n]{1,80})\]", r"*\1*", text)
    text = re.sub(r"［([^］\n]{1,80})］", r"*\1*", text)
    return text.strip()


def make_risu_card(card_fields: dict, fallback_name: str) -> dict:
    card = copy.deepcopy(DEFAULT_CARD)
    data = card["data"]
    now = int(time.time())

    data["name"] = str(card_fields.get("name") or fallback_name)
    data["description"] = enrich_description_with_story_memory(card_fields)
    data["personality"] = str(card_fields.get("personality") or "")
    data["scenario"] = str(card_fields.get("scenario") or "")
    data["first_mes"] = normalise_dialogue_marks(str(card_fields.get("first_mes") or ""))
    data["mes_example"] = normalise_dialogue_marks(str(card_fields.get("mes_example") or ""))
    data["creator_notes"] = str(card_fields.get("creator_notes") or "")
    data["system_prompt"] = str(card_fields.get("system_prompt") or "")
    data["post_history_instructions"] = str(card_fields.get("post_history_instructions") or "")
    data["alternate_greetings"] = [
        normalise_dialogue_marks(str(item))
        for item in card_fields.get("alternate_greetings", [])
        if str(item).strip()
    ] or [""]
    data["modification_date"] = now
    data["creation_date"] = now * 1000
    data["character_book"]["entries"] = build_lorebook_entries(
        card_fields.get("lorebook_entries", []),
        card_fields=card_fields,
    )
    return card


def enrich_description_with_story_memory(card_fields: dict) -> str:
    description = str(card_fields.get("description") or "").strip()
    relationship_arc = str(card_fields.get("relationship_arc") or "").strip()

    sections = [description] if description else []
    if relationship_arc:
        sections.append(f"### Relationship After the Story\n{relationship_arc}")

    return "\n\n".join(sections)


def _string_list(value) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item).strip() for item in value if str(item).strip()]


def build_lorebook_entries(raw_entries: list[dict], card_fields: dict | None = None) -> list[dict]:
    entries = []
    for idx, entry in enumerate(raw_entries):
        keys = entry.get("keys") or []
        if isinstance(keys, str):
            keys = [keys]
        keys = [str(key).strip() for key in keys if str(key).strip()]
        content = str(entry.get("content") or "").strip()
        if not keys or not content:
            continue
        name = str(entry.get("name") or keys[0])
        entries.append({
            "keys": keys,
            "content": content,
            "extensions": {},
            "enabled": True,
            "insertion_order": 900 + idx,
            "constant": False,
            "selective": False,
            "name": name,
            "comment": name,
            "case_sensitive": False,
            "use_regex": False,
        })

    if card_fields:
        # Add individual script timeline events as separate lorebook entries
        timeline = card_fields.get("event_timeline", [])
        for idx, item in enumerate(timeline):
            if not isinstance(item, dict):
                continue
            event = str(item.get("event") or "").strip()
            if not event:
                continue

            lore_keys = _string_list(item.get("lore_keys", []))
            if not lore_keys:
                # Fallback triggers if empty
                lore_keys = ["사건", "그때", "기억"]

            relationship_shift = str(item.get("relationship_shift") or "").strip()
            memory_for_chat = str(item.get("memory_for_chat") or "").strip()

            content_parts = [f"작품 속 사건: {event}"]
            if relationship_shift:
                content_parts.append(f"사건 전후 관계 변화: {relationship_shift}")
            if memory_for_chat:
                content_parts.append(f"화자의 회상 및 대화 방식: {memory_for_chat}")

            entries.append({
                "keys": lore_keys,
                "content": "\n".join(content_parts),
                "extensions": {},
                "enabled": True,
                "insertion_order": 700 + idx,
                "constant": False,
                "selective": False,
                "name": f"작품 사건 {item.get('order', idx+1)}",
                "comment": f"작품 사건 {item.get('order', idx+1)}",
                "case_sensitive": False,
                "use_regex": False,
            })

        # Add fallback general shared memory entry
        memory_content = _story_memory_lorebook_content(card_fields)
        if memory_content:
            entries.insert(0, {
                "keys": ["기억", "그때", "지난번", "우리", "약속", "처음"],
                "content": memory_content,
                "extensions": {},
                "enabled": True,
                "insertion_order": 800,
                "constant": False,
                "selective": False,
                "name": "작품 이후 공유 기억",
                "comment": "작품 이후 공유 기억",
                "case_sensitive": False,
                "use_regex": False,
            })
    return entries


def _story_memory_lorebook_content(card_fields: dict) -> str:
    parts = []
    relationship_arc = str(card_fields.get("relationship_arc") or "").strip()
    if relationship_arc:
        parts.append(f"관계 변화: {relationship_arc}")

    memories = _string_list(card_fields.get("recallable_memories", []))
    if memories:
        parts.append("회상 가능한 공유 기억:\n" + "\n".join(f"- {memory}" for memory in memories[:10]))

    timeline = card_fields.get("event_timeline", [])
    timeline_lines = []
    for item in timeline[:8]:
        if not isinstance(item, dict):
            continue
        event = str(item.get("event") or "").strip()
        memory = str(item.get("memory_for_chat") or "").strip()
        if event:
            timeline_lines.append(f"- {event}" + (f" ({memory})" if memory else ""))
    if timeline_lines:
        parts.append("작품에서 함께 겪은 사건:\n" + "\n".join(timeline_lines))

    return "\n\n".join(parts)


def export_charx_bytes(card: dict, template_bytes: bytes | None = None) -> bytes:
    output = io.BytesIO()
    if template_bytes:
        with zipfile.ZipFile(io.BytesIO(template_bytes), "r") as zin:
            with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED) as zout:
                written = set()
                for item in zin.infolist():
                    if item.filename == "card.json":
                        data = json.dumps(card, ensure_ascii=False, indent=2).encode("utf-8")
                    else:
                        data = zin.read(item.filename)
                    zout.writestr(item, data)
                    written.add(item.filename)
                if "card.json" not in written:
                    zout.writestr("card.json", json.dumps(card, ensure_ascii=False, indent=2))
    else:
        with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED) as zout:
            zout.writestr("card.json", json.dumps(card, ensure_ascii=False, indent=2))
    return output.getvalue()
