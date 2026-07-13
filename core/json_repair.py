import json
import re


def parse_json_response(response: str) -> dict:
    if not response:
        return {}

    cleaned_resp = response.strip()

    cleaned_resp = re.sub(r"^(<\|im_start\|>|<\|im_end\|>|assistant|user|\s)+", "", cleaned_resp)
    cleaned_resp = re.sub(r"(<\|im_start\|>|<\|im_end\|>|assistant|user|\s)+$", "", cleaned_resp)

    cleaned_resp = re.sub(r"<think>.*?</think>", "", cleaned_resp, flags=re.DOTALL)
    cleaned_resp = re.sub(r"<think>.*", "", cleaned_resp, flags=re.DOTALL)

    fenced_match = re.search(r"```(?:json|JSON)?\s*(.*?)\s*```", cleaned_resp, re.DOTALL)
    if fenced_match:
        cleaned_resp = fenced_match.group(1).strip()

    json_match = re.search(r"\{.*\}", cleaned_resp, re.DOTALL)
    json_str = json_match.group(0) if json_match else cleaned_resp

    if not json_str.startswith("{") and '"' in json_str and ":" in json_str:
        json_str = "{" + json_str
    if not json_str.endswith("}") and '"' in json_str and ":" in json_str:
        json_str = json_str + "}"

    lines = json_str.split("\n")
    cleaned_lines = []

    for line in lines:
        line_strip = line.strip()
        if not line_strip:
            continue

        m = re.match(r'^(\s*)"([a-zA-Z0-9_\-\s/]+):\s*"(,\s*|)$', line)
        if m:
            indent = m.group(1) or ""
            key = m.group(2)
            suffix = m.group(3) or ""
            cleaned_lines.append(f'{indent}"{key}": ""{suffix}')
            continue

        kv_match = re.match(r'^(\s*"[a-zA-Z0-9_\-\s/]+"\s*:\s*")(.*)("\s*,?\s*)$', line)
        if kv_match:
            prefix, content, suffix = kv_match.groups()
            clean_content = content.replace('\\"', '"')
            escaped_content = clean_content.replace('"', '\\"')
            line = prefix + escaped_content + suffix
            line_strip = line.strip()

        elif re.match(r'^(\s*")(.*)("\s*,?\s*)$', line):
            list_match = re.match(r'^(\s*")(.*)("\s*,?\s*)$', line)
            prefix, content, suffix = list_match.groups()
            if prefix and content and suffix:
                if content.strip() not in ("", "[", "]", "{", "}", ","):
                    clean_content = content.replace('\\"', '"')
                    escaped_content = clean_content.replace('"', '\\"')
                    line = prefix + escaped_content + suffix
                    line_strip = line.strip()

        quotes_count = line_strip.count('"') - line_strip.count('\\"')
        if quotes_count % 2 != 0:
            if line_strip.endswith(','):
                line_strip = line_strip[:-1].rstrip() + '",'
            else:
                line_strip = line_strip + '"'

        cleaned_lines.append(line_strip)

    json_str = "\n".join(cleaned_lines)
    json_str = re.sub(r'"([a-zA-Z0-9_\-\s/]+):\s*"', r'"\1": "', json_str)
    json_str = re.sub(r'([{,]\s*)([a-zA-Z0-9_\-\s/]+)\s*:', r'\1"\2":', json_str)
    json_str = re.sub(r',\s*([\]}])', r'\1', json_str)

    valid_escape_pattern = re.compile(r'(\\["\\/bfnrt]|\\u[0-9a-fA-F]{4})|\\')

    def fix_escape(match):
        if match.group(1):
            return match.group(1)
        return "\\\\"

    json_str = valid_escape_pattern.sub(fix_escape, json_str)

    stack = []
    for char in json_str:
        if char == '{':
            stack.append('}')
        elif char == '[':
            stack.append(']')
        elif char == '}':
            if stack and stack[-1] == '}':
                stack.pop()
        elif char == ']':
            if stack and stack[-1] == ']':
                stack.pop()

    while stack:
        close_token = stack.pop()
        json_str += "\n" + close_token

    try:
        return json.loads(json_str, strict=False)
    except json.JSONDecodeError as e:
        try:
            cleaned = re.sub(r"'\s*:", r'":', json_str)
            cleaned = re.sub(r":\s*'", r':"', cleaned)
            cleaned = re.sub(r"([{,]\s*)'", r'\1"', cleaned)
            cleaned = re.sub(r"'\s*([,}])", r'"\1', cleaned)
            return json.loads(cleaned, strict=False)
        except Exception:
            raise e
