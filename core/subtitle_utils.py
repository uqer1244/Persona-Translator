import re


def parse_srt_block(block: str):
    lines = block.strip().split("\n")
    timecode_idx = -1
    for i, line in enumerate(lines):
        if "-->" in line:
            timecode_idx = i
            break

    if timecode_idx == -1:
        return None, block

    header_lines = lines[:timecode_idx + 1]
    dialog_lines = lines[timecode_idx + 1:]

    header = "\n".join(header_lines)
    dialog = "\n".join(dialog_lines)
    return header, dialog


def parse_lrc_line(line: str):
    match = re.match(r'^(\[\d{2}:\d{2}[:\.]\d{2,3}\])(.*)', line.strip())
    if match:
        return match.group(1), match.group(2)
    return None, line


def preprocess_subtitle_chunk(
    chunk_text: str,
    start_index: int = 1,
    file_name: str = "",
) -> tuple[str, dict, int]:
    is_vtt = file_name.lower().endswith(".vtt") or "WEBVTT" in chunk_text
    is_srt = file_name.lower().endswith(".srt") or "-->" in chunk_text
    is_lrc = (
        file_name.lower().endswith(".lrc")
        or (
            not is_srt
            and not is_vtt
            and re.search(r'^\[\d{2}:\d{2}', chunk_text, re.MULTILINE)
        )
    )

    headers_map = {}
    simplified_blocks = []
    current_idx = start_index

    if is_srt or is_vtt:
        chunk_text = chunk_text.replace("\r\n", "\n")
        raw_blocks = chunk_text.split("\n\n")

        for block in raw_blocks:
            if not block.strip():
                continue

            if block.strip() == "WEBVTT":
                headers_map["WEBVTT"] = "WEBVTT"
                simplified_blocks.append("[#WEBVTT]")
                continue

            header, dialog = parse_srt_block(block)
            if header:
                headers_map[str(current_idx)] = header
                simplified_blocks.append(f"[#{current_idx}] {dialog}")
                current_idx += 1
            else:
                simplified_blocks.append(dialog)

        simplified_text = "\n\n".join(simplified_blocks)

    elif is_lrc:
        chunk_text = chunk_text.replace("\r\n", "\n")
        lines = chunk_text.split("\n")

        for line in lines:
            if not line.strip():
                simplified_blocks.append("")
                continue
            header, dialog = parse_lrc_line(line)
            if header:
                headers_map[str(current_idx)] = header
                simplified_blocks.append(f"[#{current_idx}] {dialog}")
                current_idx += 1
            else:
                simplified_blocks.append(line)

        simplified_text = "\n".join(simplified_blocks)

    else:
        simplified_text = chunk_text

    return simplified_text, headers_map, current_idx


def postprocess_subtitle_chunk(llm_output: str, headers_map: dict, file_name: str = "") -> str:
    if not headers_map:
        return llm_output

    is_lrc = file_name.lower().endswith(".lrc")

    pattern = re.compile(r'\[#(\w+)\]\s*(.*?)(?=\[#\w+\]|$)', re.DOTALL)
    matches = pattern.findall(llm_output)

    reconstructed_blocks = []
    matched_indices = set()

    for idx_str, text in matches:
        idx_str = idx_str.strip()
        text = text.strip()

        if idx_str == "WEBVTT":
            reconstructed_blocks.append("WEBVTT")
            matched_indices.add("WEBVTT")
            continue

        if idx_str in headers_map:
            header = headers_map[idx_str]
            if is_lrc:
                reconstructed_blocks.append(f"{header}{text}")
            else:
                reconstructed_blocks.append(f"{header}\n{text}")
            matched_indices.add(idx_str)

    if len(matched_indices) < len(headers_map):
        cleaned_text = re.sub(r'\[#\w+\]', '', llm_output).strip()

        if is_lrc:
            llm_blocks = [b.strip() for b in cleaned_text.split("\n") if b.strip()]
        else:
            llm_blocks = [b.strip() for b in cleaned_text.split("\n\n") if b.strip()]

        reconstructed_blocks = []
        sorted_keys = sorted([k for k in headers_map.keys() if k != "WEBVTT"], key=lambda x: int(x))
        if "WEBVTT" in headers_map:
            reconstructed_blocks.append("WEBVTT")

        for i, key in enumerate(sorted_keys):
            header = headers_map[key]
            trans_block = llm_blocks[i] if i < len(llm_blocks) else ""
            if is_lrc:
                reconstructed_blocks.append(f"{header}{trans_block}")
            else:
                reconstructed_blocks.append(f"{header}\n{trans_block}")

    if is_lrc:
        return "\n".join(reconstructed_blocks)
    return "\n\n".join(reconstructed_blocks)
