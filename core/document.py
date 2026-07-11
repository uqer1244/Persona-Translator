import re
from pypdf import PdfReader


def extract_text_from_pdf(pdf_file) -> str:
    """
    Extracts text from PDF file.
    """
    reader = PdfReader(pdf_file)
    text_list = []
    for page in reader.pages:
        text = page.extract_text()
        if text:
            text_list.append(text)
    return "\n".join(text_list)


def clean_pdf_linebreaks(text: str) -> str:
    """
    Cleans up broken lines resulting from vertical text or PDF layout issues by merging them logically.
    """
    if not text:
        return ""
    
    # Standardize line endings
    text = text.replace("\r\n", "\n")
    lines = [line.strip() for line in text.split("\n")]
    result_lines = []
    current_line = ""
    
    for line in lines:
        if not line:
            if current_line:
                result_lines.append(current_line)
                current_line = ""
            result_lines.append("")
            continue
            
        # If line ends with sentence ending in Korean/Japanese or stage directions, merge appropriately
        if current_line:
            current_line += " " + line
        else:
            current_line = line
            
        if line.endswith((".", "?", "!", "\"", "”", "」", "』", ")", "）", "]", "］")):
            result_lines.append(current_line)
            current_line = ""
            
    if current_line:
        result_lines.append(current_line)
        
    return "\n".join(result_lines)


def clean_markdown(text: str) -> str:
    """
    Cleans markdown backticks (e.g. ```plaintext ...) frequently outputted by VLMs.
    """
    if not text:
        return ""
    text = re.sub(r"^```[a-zA-Z0-9]*\n", "", text)
    text = re.sub(r"\n```$", "", text)
    text = re.sub(r"^```", "", text)
    text = re.sub(r"```$", "", text)
    return text.strip()


def chunk_srt(srt_text: str, target_chunk_size: int = 400) -> list[str]:
    """
    Dynamically groups SRT subtitle blocks based on target character count to limit LLM calls and VRAM spike.
    """
    if not srt_text.strip():
        return []
        
    # Standardize line endings
    srt_text = srt_text.replace("\r\n", "\n")
    # Split into blocks by double newlines
    raw_blocks = srt_text.split("\n\n")
    
    blocks = []
    for b in raw_blocks:
        if b.strip():
            blocks.append(b.strip())
            
    chunks = []
    current_chunk = []
    current_len = 0
    
    for block in blocks:
        block_len = len(block)
        if current_len + block_len > target_chunk_size and current_chunk:
            chunks.append("\n\n".join(current_chunk))
            current_chunk = [block]
            current_len = block_len
        else:
            current_chunk.append(block)
            current_len += block_len + 2 # account for newline split
            
    if current_chunk:
        chunks.append("\n\n".join(current_chunk))
        
    return chunks


def chunk_text(text: str, chunk_size: int = 400) -> list[str]:
    """
    Splits plain text into scene-aware chunks. Detects scene transitions, BGM/SE markers,
    or speaker changes to split gracefully rather than cutting in the middle of sentences.
    """
    if not text:
        return []
        
    text = text.replace("\r\n", "\n")
    lines = text.split("\n")
    
    chunks = []
    current_chunk = []
    current_len = 0
    
    # Markers indicating scene/logical breaks
    scene_break_patterns = [
        re.compile(r'^\s*\[\s*(?:[sS]cene|[eE]pisode|[tT]rack|파트|트랙|씬)\s*\d+\s*\]'),
        re.compile(r'^\s*#\d+'),
        re.compile(r'^\s*(?:[bB]gm|[sS]e|BGM|SE)\s*[:：]'),
    ]
    
    for line in lines:
        line_strip = line.strip()
        is_boundary = False
        
        # Check if the line represents a scene boundary
        for pattern in scene_break_patterns:
            if pattern.match(line_strip):
                is_boundary = True
                break
                
        # Split chunk if we exceed target size, or if we hit a boundary
        if (current_len + len(line) > chunk_size or is_boundary) and current_chunk:
            chunks.append("\n".join(current_chunk))
            current_chunk = [line]
            current_len = len(line)
        else:
            current_chunk.append(line)
            current_len += len(line) + 1
            
    if current_chunk:
        chunks.append("\n".join(current_chunk))
        
    return chunks
