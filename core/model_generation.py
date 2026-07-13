def model_family(model, processor) -> str:
    from core.model_runtime import wrap_model_runtime

    runtime = wrap_model_runtime(model, processor)
    if runtime.backend_key in {"mlx", "openrouter", "api"}:
        return runtime.family

    config = getattr(model, "config", None)
    model_type = str(getattr(config, "model_type", "") or "").lower()
    archs = [str(a).lower() for a in (getattr(config, "architectures", []) or [])]
    template = str(getattr(processor, "chat_template", "") or "")
    tokenizer = getattr(processor, "tokenizer", None)
    template += str(getattr(tokenizer, "chat_template", "") or "")

    if "qwen" in model_type or any("qwen" in a for a in archs) or "qwen" in template.lower():
        return "qwen"
    if "gemma" in model_type or any("gemma" in a for a in archs) or "gemma" in template.lower():
        return "gemma"
    if hasattr(processor, "image_processor"):
        return "vlm"
    return "text"


def json_rules(model, processor) -> str:
    if model_family(model, processor) == "qwen":
        return """[JSON 형식 엄격 준수 규칙]
1. 먼저 <think> 태그 내에서 필요한 분석 단계를 자유롭게 서술해도 좋습니다.
2. 태그를 닫은 후에는 반드시 위에 지정된 JSON 형식으로만 결과물을 작성하세요.
3. JSON 앞뒤에 마크다운 코드펜스(```json), 인삿말, 설명문을 붙이지 마세요.
4. 모든 문자열 값 내부에서 일반 큰따옴표를 쓰지 말고 작은따옴표 또는 한국어 따옴표를 사용하세요."""

    return """[JSON 형식 엄격 준수 규칙]
1. 오직 JSON 객체 하나만 출력하세요.
2. <think> 태그, 분석 과정, 인삿말, 설명문, 마크다운 코드펜스(```json)를 절대 출력하지 마세요.
3. 첫 글자는 반드시 { 이고 마지막 글자는 반드시 } 이어야 합니다.
4. 모든 문자열 값 내부에서 일반 큰따옴표를 쓰지 말고 작은따옴표 또는 한국어 따옴표를 사용하세요."""


def json_correction_rules(model, processor) -> str:
    if model_family(model, processor) == "qwen":
        return """[JSON 형식 엄격 준수 규칙]
1. 먼저 <think> 태그 내에서 필요한 분석 단계를 자유롭게 서술해도 좋습니다.
2. 태그를 닫은 후에는 반드시 아래 예시된 JSON 형식으로만 결과물을 작성하세요.
3. 다른 설명이나 마크다운 백틱은 일절 생략하십시오."""

    return """[JSON 형식 엄격 준수 규칙]
1. 오직 문법적으로 유효한 JSON 객체 하나만 출력하세요.
2. <think> 태그, 분석 과정, 설명, 마크다운 백틱은 일절 생략하십시오.
3. 첫 글자는 반드시 { 이고 마지막 글자는 반드시 } 이어야 합니다."""


def generate_text(
    model,
    processor,
    prompt: str,
    image_paths: list[str] | None = None,
    max_tokens: int = 1024,
    temp: float = 0.1,
    repetition_penalty: float = 1.1,
    force_json: bool = False,
) -> str:
    from core.utils import has_repetition
    from core.model_runtime import ModelRuntime

    image_paths = image_paths or []
    prompt_content = prompt
    if image_paths and "<image>" not in prompt:
        prompt_content = "<image>\n" + prompt

    if isinstance(model, ModelRuntime):
        runtime = model
        model, processor = runtime.unwrap()
        if image_paths and not runtime.supports_vision:
            image_paths = []

    try:
        from core.openrouter import OpenRouterClient
        if isinstance(model, OpenRouterClient):
            return _generate_openrouter_text(
                model,
                prompt_content,
                image_paths,
                max_tokens=max_tokens,
                temp=temp,
            )
    except ImportError:
        pass

    is_vlm_model = hasattr(processor, "image_processor")
    stream_generate, formatted_prompt, sampler, logits_processors = _prepare_local_generation(
        model,
        processor,
        prompt_content,
        image_count=len(image_paths),
        force_json=force_json,
        temp=temp,
        repetition_penalty=repetition_penalty,
    )

    max_retries = 3
    output = ""
    for retry in range(max_retries):
        current_temp = temp
        current_penalty = repetition_penalty
        if retry > 0:
            current_temp = min(0.7, temp + 0.2 * retry)
            current_penalty = repetition_penalty + 0.15 * retry
            print(f"[RETRY] Loop detected, retrying {retry}/{max_retries-1} with temp={current_temp:.2f}, penalty={current_penalty:.2f}")

        output = ""
        if is_vlm_model:
            generator = stream_generate(
                model,
                processor,
                prompt=formatted_prompt,
                image=image_paths or None,
                temp=current_temp,
                max_tokens=max_tokens,
                repetition_penalty=current_penalty,
                repetition_context_size=100,
                seed=42,
            )
        else:
            from mlx_lm.sample_utils import make_sampler, make_logits_processors

            sampler = make_sampler(temp=current_temp)
            logits_processors = make_logits_processors(
                repetition_penalty=current_penalty,
                repetition_context_size=100,
            )
            generator = stream_generate(
                model,
                processor,
                prompt=formatted_prompt,
                max_tokens=max_tokens,
                sampler=sampler,
                logits_processors=logits_processors,
            )

        loop_detected = False
        for response in generator:
            output += response.text
            if has_repetition(output):
                print("[WARNING] Repetition loop detected! Stopping stream.")
                loop_detected = True
                break

        if force_json and not is_vlm_model and not output.strip().startswith("{"):
            output = "{" + output

        if not loop_detected:
            return output

    return output


def _generate_openrouter_text(model, prompt_content: str, image_paths: list[str], max_tokens: int, temp: float) -> str:
    import base64
    import os

    from core.document import clean_markdown
    from core.utils import has_repetition, strip_repetition

    content = []
    for img_path in image_paths:
        if os.path.exists(img_path):
            with open(img_path, "rb") as f:
                b64_data = base64.b64encode(f.read()).decode("utf-8")
            mime = "image/png" if img_path.lower().endswith(".png") else "image/jpeg"
            content.append({
                "type": "image_url",
                "image_url": {"url": f"data:{mime};base64,{b64_data}"},
            })

    if content:
        content.append({"type": "text", "text": prompt_content})
        messages = [{"role": "user", "content": content}]
    else:
        messages = [{"role": "user", "content": prompt_content}]

    max_retries = 3
    for retry in range(max_retries):
        current_temp = temp if retry == 0 else min(0.7, temp + 0.2 * retry)
        try:
            generator = model.generate_stream(messages, temp=current_temp, max_tokens=max_tokens)
            output = ""
            for response in generator:
                output += response.text
                if has_repetition(output):
                    output = strip_repetition(output)
                    break
            return clean_markdown(output)
        except Exception as e:
            if retry == max_retries - 1:
                raise e
            print(f"[OpenRouter RETRY] Error occurred, retrying: {e}")

    return ""


def _prepare_local_generation(
    model,
    processor,
    prompt_content: str,
    image_count: int,
    force_json: bool,
    temp: float,
    repetition_penalty: float,
):
    if hasattr(processor, "image_processor"):
        from mlx_vlm.generate import stream_generate
        from mlx_vlm.prompt_utils import apply_chat_template

        messages = [{"role": "user", "content": prompt_content}]
        formatted_prompt = apply_chat_template(
            processor,
            model.config,
            messages,
            num_images=image_count,
            num_audios=0,
        )
        return stream_generate, formatted_prompt, None, None

    from mlx_lm import stream_generate
    from mlx_lm.sample_utils import make_sampler, make_logits_processors

    messages = [{"role": "user", "content": prompt_content}]
    formatted_prompt = processor.apply_chat_template(messages, tokenize=False, add_generation_prompt=True)
    if force_json:
        if formatted_prompt.endswith("<think>\n"):
            formatted_prompt = formatted_prompt[:-8]
        elif formatted_prompt.endswith("<think>"):
            formatted_prompt = formatted_prompt[:-7]
        if not formatted_prompt.endswith("{"):
            formatted_prompt += "{"

    sampler = make_sampler(temp=temp)
    logits_processors = make_logits_processors(
        repetition_penalty=repetition_penalty,
        repetition_context_size=100,
    )
    return stream_generate, formatted_prompt, sampler, logits_processors
