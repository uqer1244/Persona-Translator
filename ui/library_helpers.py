import io
import os

import streamlit as st
from PIL import Image, ImageFilter


def get_nsfw_status(name: str, path: str) -> bool:
    """Gets manually assigned NSFW status only."""
    return os.path.exists(os.path.join(path, ".nsfw"))


def set_nsfw_status(path: str, is_nsfw: bool) -> None:
    """Sets manual NSFW status by creating override files."""
    nsfw_file = os.path.join(path, ".nsfw")
    sfw_file = os.path.join(path, ".sfw")
    if is_nsfw:
        _remove_if_exists(sfw_file)
        with open(nsfw_file, "w", encoding="utf-8") as f:
            f.write("1")
    else:
        _remove_if_exists(nsfw_file)
        with open(sfw_file, "w", encoding="utf-8") as f:
            f.write("1")


def _remove_if_exists(path: str) -> None:
    if not os.path.exists(path):
        return
    try:
        os.remove(path)
    except Exception:
        pass


@st.cache_data(show_spinner=False)
def get_display_image_cached(image_path: str, blur: bool, blur_strength: int = 20) -> bytes:
    """Loads, resizes, and optionally blurs the cover image, caching the result."""
    try:
        img = Image.open(image_path)
        img = img.convert("RGB")
        width, height = img.size
        new_width = 300
        new_height = int(height * (new_width / width))
        img = img.resize((new_width, new_height), Image.Resampling.LANCZOS)
        if blur and blur_strength > 0:
            img = img.filter(ImageFilter.GaussianBlur(radius=blur_strength))

        buf = io.BytesIO()
        img.save(buf, format="JPEG", quality=85)
        return buf.getvalue()
    except Exception:
        try:
            with open(image_path, "rb") as f:
                return f.read()
        except Exception:
            return b""


def get_dir_tree(startpath: str) -> str:
    tree = []
    ignored_dirs = {"translation_backup", "temp_backups", "images"}
    icon_by_ext = {
        ".txt": "📝",
        ".srt": "📝",
        ".pdf": "📝",
        ".png": "🖼️",
        ".jpg": "🖼️",
        ".jpeg": "🖼️",
        ".webp": "🖼️",
        ".mp3": "🎵",
        ".wav": "🎵",
        ".flac": "🎵",
        ".m4a": "🎵",
    }

    for root, dirs, files in os.walk(startpath):
        dirs[:] = [d for d in dirs if not d.startswith(".") and d not in ignored_dirs]
        level = root.replace(startpath, "").count(os.sep)
        indent = "  " * level
        folder_name = os.path.basename(root)
        if folder_name:
            tree.append(f"{indent}📁 {folder_name}/")

        subindent = "  " * (level + 1)
        for filename in sorted(files):
            if filename.startswith("."):
                continue
            ext = os.path.splitext(filename)[1].lower()
            tree.append(f"{subindent}{icon_by_ext.get(ext, '📄')} {filename}")

    return "\n".join(tree)
