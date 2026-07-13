import os
import json
import re
from core.chat_utils import build_rag_corpus, BM25Okapi, clean_and_tokenize
from core.progress_store import BACKUP_ROOT


class PromptCacheManager:
    """
    MLX KVCache와 토큰 히스토리를 정렬하여 중복 인코딩을 방지하는 캐시 관리 클래스
    """
    def __init__(self, model):
        from mlx_lm.utils import make_prompt_cache
        self.prompt_cache = make_prompt_cache(model)
        self.cached_tokens = []

    def get_incremental_tokens(self, formatted_prompt: str, processor) -> list[int]:
        if hasattr(processor, "tokenizer"):
            tokenizer = processor.tokenizer
        else:
            tokenizer = processor
            
        all_tokens = tokenizer.encode(formatted_prompt)
        
        # 이전 캐싱된 토큰들과 매칭되는 공통 접두사 확인
        common_len = 0
        for i in range(min(len(self.cached_tokens), len(all_tokens))):
            if self.cached_tokens[i] == all_tokens[i]:
                common_len += 1
            else:
                break
                
        # 매칭 일치도가 너무 낮으면(예: 대화방 리셋 등) 캐시 리셋
        if common_len < len(self.cached_tokens) * 0.9:
            self.prompt_cache.reset()
            self.cached_tokens = []
            common_len = 0
            
        # 역전 현상이 생겨도 리셋
        if common_len < len(self.cached_tokens):
            self.prompt_cache.reset()
            self.cached_tokens = all_tokens
            return all_tokens
            
        new_tokens = all_tokens[common_len:]
        self.cached_tokens.extend(new_tokens)
        return new_tokens


class ChatEngine:
    """
    RAG 검색, 시스템 프롬프트 조립 및 mlx_vlm을 통한 실시간 대화 추론을 제어하는 엔진 클래스
    """
    def __init__(self):
        self.project_name = None
        self.persona = {}
        self.glossary_list = []
        self.rag_items = []
        self.bm25 = None
        self.model = None
        self.processor = None
        self.model_path = None
        self.model_loaded = False
        self.prompt_cache = None
        
        # 서사 제어 및 인지 고도화용 신규 상태 필드
        self.script_summary = {}
        self.current_anchor_idx = 0
        self.last_max_score = 0.0
        self.last_steered_mode = "대기"
        self.history_rag_items = [] # 장기 대화 RAG 아이템

    def load_model(self, model_path: str):
        """
        mlx_vlm 모델을 로컬 폴더에서 로드합니다. Streamlit 컨텍스트와 독립적입니다.
        """
        import mlx.core as mx
        import gc

        mx.clear_cache()
        gc.collect()

        # Read config.json to decide mlx_lm vs mlx_vlm loading
        is_vlm = False
        if os.path.isdir(model_path):
            config_json_path = os.path.join(model_path, "config.json")
            if os.path.exists(config_json_path):
                try:
                    import json
                    with open(config_json_path, "r", encoding="utf-8") as f:
                        cfg = json.load(f)
                    
                    model_type = cfg.get("model_type", "").lower()
                    archs = [a.lower() for a in cfg.get("architectures", [])]
                    is_qwen = "qwen" in model_type or any("qwen" in a for a in archs) or "qwen" in model_path.lower()
                    
                    if is_qwen:
                        is_vlm = False
                    elif cfg.get("language_model_only", False):
                        is_vlm = False
                    elif "vision_config" in cfg or "vision_tower" in cfg:
                        is_vlm = True
                    elif any("ConditionalGeneration" in a for a in cfg.get("architectures", [])):
                        is_vlm = True
                except Exception:
                    pass

        try:
            if is_vlm:
                from mlx_vlm import load
                self.model, self.processor = load(model_path)
            else:
                from mlx_lm import load
                self.model, self.processor = load(model_path)
        except Exception as e:
            if is_vlm:
                print(f"[ChatEngine] Failed loading with mlx_vlm: {e}. Retrying with mlx_lm...")
                from mlx_lm import load
                self.model, self.processor = load(model_path)
            else:
                raise e
        self.model_path = model_path
        self.model_loaded = True

        mx.clear_cache()
        gc.collect()
        print("[ChatEngine] Model loaded successfully.")

    def unload_model(self):
        """
        VRAM 점유 해제를 위해 모델을 언로드하고 캐시를 비웁니다.
        """
        self.model = None
        self.processor = None
        self.model_loaded = False
        self.prompt_cache = None
        import mlx.core as mx
        import gc
        mx.clear_cache()
        gc.collect()
        print("[ChatEngine] Model unloaded.")

    def load_project(self, project_name: str):
        """
        프로젝트 백업 폴더(projects/{project_name})에서 페르소나 및 대본 데이터를 로드합니다.
        """
        self.project_name = project_name
        project_dir = os.path.join(BACKUP_ROOT, project_name)
        if not os.path.exists(project_dir):
            raise FileNotFoundError(f"Project directory {project_name} not found.")

        # 1. persona.json 로드
        persona_path = os.path.join(project_dir, "persona.json")
        if os.path.exists(persona_path):
            with open(persona_path, "r", encoding="utf-8") as f:
                data = json.load(f)
                self.persona = data.get("persona", {})
                self.glossary_list = data.get("glossary_data", [])
                self.script_summary = data.get("script_summary", {})
        else:
            self.persona = {}
            self.glossary_list = []
            self.script_summary = {}

        # 2. progress.json 로드 후 RAG 코퍼스 구축
        progress_path = os.path.join(project_dir, "progress.json")
        if os.path.exists(progress_path):
            with open(progress_path, "r", encoding="utf-8") as f:
                progress_data = json.load(f)
                self.rag_items = build_rag_corpus(progress_data)

                # BM25 초기화
                corpus_tokens = [item["tokens"] for item in self.rag_items]
                if corpus_tokens:
                    self.bm25 = BM25Okapi(corpus_tokens)
                else:
                    self.bm25 = None
        else:
            self.rag_items = []
            self.bm25 = None
            
        print(f"[ChatEngine] Project '{project_name}' loaded. RAG Items: {len(self.rag_items)}")

    def search_rag(self, query: str, top_n: int = 3) -> list[dict]:
        """
        사용자 입력어에 매칭되는 대본 라인(원문 & 번역)을 검색합니다.
        """
        if not self.bm25 or not self.rag_items:
            return []

        from core.chat_utils import clean_and_tokenize
        query_tokens = clean_and_tokenize(query)
        if not query_tokens:
            return []

        scores = self.bm25.get_scores(query_tokens)

        # 0점 초과 매칭 스코어 필터링 및 랭킹 정렬
        ranked_indices = sorted(
            [idx for idx, score in enumerate(scores) if score > 0.05],
            key=lambda idx: scores[idx],
            reverse=True
        )

        results = []
        for idx in ranked_indices[:top_n]:
            results.append({
                "original": self.rag_items[idx]["original"],
                "translated": self.rag_items[idx]["translated"],
                "score": scores[idx],
                "index": idx
            })
            
        # 가장 스코어가 높은 구절의 인덱스를 현재 앵커 지점으로 트래킹 (0.1 이상일 때)
        if results and results[0]["score"] > 0.1:
            self.current_anchor_idx = results[0]["index"]
            self.last_max_score = results[0]["score"]
        else:
            self.last_max_score = results[0]["score"] if results else 0.0
            
        return results

    def search_history_rag(self, query: str, history: list[dict], top_n: int = 2) -> list[str]:
        """
        최근 6턴을 제외한 과거 대화 히스토리 내역 중 사용자의 입력과 매칭되는 대화를 검색해 인용구로 가져옵니다.
        """
        if len(history) <= 6:
            return []
            
        older_turns = history[:-6]
        corpus_docs = []
        # user와 assistant의 대화를 2턴씩 페어링하여 문서 조각화
        for idx in range(0, len(older_turns) - 1, 2):
            if idx + 1 < len(older_turns):
                user_msg = older_turns[idx].get("content", "")
                assistant_msg = older_turns[idx+1].get("content", "")
                if user_msg.strip() or assistant_msg.strip():
                    corpus_docs.append(f"사용자: {user_msg}\n캐릭터: {assistant_msg}")
                    
        if not corpus_docs:
            return []
            
        from core.chat_utils import clean_and_tokenize
        doc_tokens = [clean_and_tokenize(doc) for doc in corpus_docs]
        from core.chat_utils import BM25Okapi as TempBM25
        
        try:
            temp_bm25 = TempBM25(doc_tokens)
            query_tokens = clean_and_tokenize(query)
            if not query_tokens:
                return []
                
            scores = temp_bm25.get_scores(query_tokens)
            ranked = sorted(
                [i for i, s in enumerate(scores) if s > 0.1],
                key=lambda i: scores[i],
                reverse=True
            )
            
            hits = []
            for idx in ranked[:top_n]:
                hits.append(corpus_docs[idx])
            return hits
        except Exception:
            return []

    def build_system_prompt(self, user_message: str, history: list[dict]) -> tuple[str, list[dict]]:
        """
        대본 전체 요약 정보, 페르소나 캐릭터 지침, 단어장, 대본 RAG 및 History RAG를 조합해 시스템 프롬프트를 구성합니다.
        """
        # 1. 대본 전체 요약 맥락 구성 (서사 인지 레이어)
        summary_guide = ""
        if self.script_summary:
            spk = self.script_summary.get("speaker_name", "화자")
            lis = self.script_summary.get("listener_role", "청자")
            sit = self.script_summary.get("situation", "상황 정보 없음")
            story = self.script_summary.get("story", "전체 줄거리 흐름 없음")
            summary_guide = f"""
[전체 대본 서사 구조 및 세계관]
- 당신(화자/주인공): {spk}
- 상대방(사용자/듣는이): {lis}
- 작품 전체 상황극 배경 설정: {sit}
- 전체 줄거리 흐름:
{story}
"""

        # 2. 페르소나 설정
        tone = self.persona.get("tone", "자연스러운 대화 말투")
        relationship = self.persona.get("relationship", "화자와 청자의 깊은 유대 관계")
        situation = self.persona.get("situation", "상황극 배경 정보 없음")
        key_rules = self.persona.get("key_rules", [])

        persona_guide = f"- 당신의 말투 및 어조: {tone}\n"
        persona_guide += f"- 당신(화자)과 사용자(청자)의 관계: {relationship}\n"
        persona_guide += f"- 상황극 배경 및 맥락: {situation}\n"
        
        if key_rules:
            rules_str = "\n".join([f"  * {rule}" for rule in key_rules])
            persona_guide += f"- 연기 규칙:\n{rules_str}\n"

        # 3. 용어집 룰 추가
        glossary_guide = ""
        valid_glossaries = [g for g in self.glossary_list if g.get("원어 (Source)") and g.get("번역어 (Target)")]
        if valid_glossaries:
            glossary_guide = "\n<glossary>\n"
            for item in valid_glossaries:
                src = item["원어 (Source)"].strip()
                tgt = item["번역어 (Target)"].strip()
                ctx = item.get("설명/뉘앙스 (Context)", "").strip()
                is_proper = item.get("고유명사 (Proper Noun)", False)
                proper_str = " [고유명사]" if is_proper else ""
                ctx_str = f" ({ctx})" if ctx else ""
                glossary_guide += f"  - 단어 '{src}'를 사용할 때는 상황에 어울리게{proper_str} 고정어 '{tgt}' 혹은 어투에 맞게 표현하세요.{ctx_str}\n"
            glossary_guide += "</glossary>\n"

        # 4. RAG 대본 매칭 구절 및 Steering 모드 판단
        rag_hits = self.search_rag(user_message, top_n=3)
        
        # 앵커 씬 텍스트 구하기 (Narrative Gravity 용)
        anchor_scene_text = ""
        if self.rag_items and 0 <= self.current_anchor_idx < len(self.rag_items):
            anchor_scene_text = f"대본 라인 번호 {self.current_anchor_idx+1}: {self.rag_items[self.current_anchor_idx]['translated']}"

        # Attention Steering 프롬프트 구성
        steering_guide = ""
        if self.last_max_score >= 0.15:
            self.last_steered_mode = "레일 추종 (대본 중심)"
            rag_guide = ""
            if rag_hits:
                rag_guide = "\n[Hidden Hint: 당시 원작 대본에서 연기했던 씬 내용입니다. 대화 흐름상 이 내용을 적극 인용하거나 대사의 방향성을 정확히 따라가며 대화하세요]\n"
                for hit in rag_hits:
                    rag_guide += f"  - (원문 대사) {hit['original']} => (번역 대사) {hit['translated']}\n"
                rag_guide += "\n"
            steering_guide = f"""
[서사 제어 모드: 레일 추종 (대본 중심)]
- 사용자가 현재 대본 상황 및 전개 흐름에 연관성 높은 대화를 시도했습니다.
- 아래 [Hidden Hint] 대본의 대사와 감정선, 연출 방향을 적극 모방 및 인용하여 매끄럽게 서사를 이어가세요.
{rag_guide}
"""
        else:
            self.last_steered_mode = "탈레일 분기 (애드립 & 회귀 유도)"
            steering_guide = f"""
[서사 제어 모드: 탈레일 자유 분기 (애드립 및 복귀 회귀)]
- 사용자가 대본에 전혀 서술되지 않은 돌발 행동이나 딴청을 부리는 대화를 하였습니다.
- 대본 대사를 억지로 인용하려 하지 마시고, 오직 캐릭터 페르소나(말투, 성격, 행동 규칙)에만 기초하여 아주 자연스럽고 매력적인 **애드립(임기응변)**으로 대화에 응해주세요.
- **[서사적 중력 (Narrative Gravity)]**: 자연스럽게 애드립 답변을 마친 뒤, 대화의 마지막 1~2문장에는 은근슬쩍 원래 흘러갔어야 할 대본의 상황인 **'{anchor_scene_text}'**으로 대화의 주도권을 끌어와 회귀시키도록 말을 건네세요.
"""

        # 5. Dynamic History RAG (이전 기억)
        history_hits = self.search_history_rag(user_message, history)
        history_guide = ""
        if history_hits:
            history_guide = "\n[이전 대화에서 나눈 추가 설정 및 약속 정보]\n"
            for hit in history_hits:
                history_guide += f"- 아까 나눈 대화 내용:\n{hit}\n"
            history_guide += "\n위의 이전 대화 내역에서 합의한 약속, 사건, 추가된 관계를 기억하고 답변에 모순되지 않게 반영하십시오.\n"

        system_prompt = f"""당신은 ASMR 상황극 및 대본 속 주인공 캐릭터입니다. 
주어진 캐릭터 가이드라인, 대본 전체의 흐름, 그리고 현재 서사 제어 지침을 완벽히 체화하여 사용자와 실시간 대화(롤플레잉)를 이어가세요.

{summary_guide}

[캐릭터 연기 가이드라인]
{persona_guide}
{glossary_guide}
{steering_guide}
{history_guide}

[대화 포맷팅 규칙]
1. 행동 묘사, 감정 상태, 혹은 오디오 효과음(예: 숨소리, 옷자락 스치는 소리 등)을 묘사할 때는 반드시 문장 곳곳에 대괄호 `[...]` 기호를 감싸 표현하세요. (예: "너만을 위해서 코코아를 달게 끓여왔어... [볼을 살짝 붉히며 머그잔을 건넨다] 뜨거우니까 조심해서 마셔.")
2. 대화에 어울리지 않는 해설이나, XML 태그, 프롬프트 내용을 절대로 직접 노출하지 마십시오.
3. 오직 캐릭터로서 대화하는 대사 및 지시문만 출력해야 합니다.
"""
        return system_prompt, rag_hits

    def generate_chat_response_stream(self, user_message: str, history: list[dict], temp: float = 0.7, repetition_penalty: float = 1.15):
        """
        FastAPI SSE에 직접 스트리밍 데이터를 전달할 수 있는 제너레이터 함수입니다.
        """
        if not self.model_loaded:
            yield json.dumps({"event": "error", "data": "Model not loaded. Please load a model first."}, ensure_ascii=False) + "\n"
            return

        # 시스템 프롬프트 및 RAG 계산
        system_prompt, rag_hits = self.build_system_prompt(user_message, history)

        # 1. RAG 매칭 결과 클라이언트에 우선 전달
        yield json.dumps({"event": "rag_hits", "data": rag_hits}, ensure_ascii=False) + "\n"

        # 2. 메시지 히스토리 조립
        messages = []
        messages.append({"role": "system", "content": system_prompt})
        
        # 이전 대화 턴 추가
        for turn in history:
            messages.append({"role": turn["role"], "content": turn["content"]})
            
        # 현재 메시지 추가
        messages.append({"role": "user", "content": user_message})

        try:
            from core.openrouter import OpenRouterClient
            if isinstance(self.model, OpenRouterClient):
                generator = self.model.generate_stream(messages, temp=temp, max_tokens=1000)
                for response in generator:
                    yield json.dumps({"event": "token", "data": response.text}, ensure_ascii=False) + "\n"
                return
        except ImportError:
            pass

        is_vlm_model = hasattr(self.processor, "image_processor")

        if is_vlm_model:
            from mlx_vlm.generate import stream_generate
            from mlx_vlm.prompt_utils import apply_chat_template
        else:
            from mlx_lm import stream_generate
            from mlx_lm.sample_utils import make_sampler, make_logits_processors

        try:
            if is_vlm_model:
                formatted_prompt = apply_chat_template(
                    self.processor,
                    self.model.config,
                    messages,
                    num_images=0,
                    num_audios=0
                )
            else:
                formatted_prompt = self.processor.apply_chat_template(messages, tokenize=False, add_generation_prompt=True)

            if is_vlm_model:
                generator = stream_generate(
                    self.model,
                    self.processor,
                    prompt=formatted_prompt,
                    temp=temp,
                    max_tokens=1000,
                    repetition_penalty=repetition_penalty,
                    repetition_context_size=100,
                    seed=42,
                )
            else:
                if self.prompt_cache is None:
                    self.prompt_cache = PromptCacheManager(self.model)

                import mlx.core as mx
                incremental_tokens = self.prompt_cache.get_incremental_tokens(formatted_prompt, self.processor)
                incremental_array = mx.array(incremental_tokens)

                sampler = make_sampler(temp=temp)
                logits_processors = make_logits_processors(
                    repetition_penalty=repetition_penalty,
                    repetition_context_size=100
                )
                generator = stream_generate(
                    self.model,
                    self.processor,
                    prompt=incremental_array,
                    max_tokens=1000,
                    sampler=sampler,
                    logits_processors=logits_processors,
                    prompt_cache=self.prompt_cache.prompt_cache,
                )

            # 3. 토큰 실시간 전송
            for response in generator:
                yield json.dumps({"event": "token", "data": response.text}, ensure_ascii=False) + "\n"
                if self.prompt_cache is not None and not is_vlm_model:
                    if hasattr(response, "token"):
                        self.prompt_cache.cached_tokens.append(response.token)

        except Exception as e:
            yield json.dumps({"event": "error", "data": str(e)}, ensure_ascii=False) + "\n"
        finally:
            import mlx.core as mx
            import gc
            mx.clear_cache()
            gc.collect()
