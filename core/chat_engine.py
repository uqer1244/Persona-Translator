import os
import json
import re
from core.chat_utils import build_rag_corpus, BM25Okapi, clean_and_tokenize
from core.progress_store import BACKUP_ROOT

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

    def load_model(self, model_path: str):
        """
        mlx_vlm 모델을 로컬 폴더에서 로드합니다. Streamlit 컨텍스트와 독립적입니다.
        """
        import mlx.core as mx
        import gc

        # 메모리 청소
        mx.clear_cache()
        gc.collect()
        mx.set_cache_limit(0)

        print(f"[ChatEngine] Loading model from {model_path}...")
        from mlx_vlm import load
        self.model, self.processor = load(model_path)
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
        import mlx.core as mx
        import gc
        mx.clear_cache()
        gc.collect()
        print("[ChatEngine] Model unloaded.")

    def load_project(self, project_name: str):
        """
        프로젝트 백업 폴더(DLdata/{project_name})에서 페르소나 및 대본 데이터를 로드합니다.
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
        else:
            self.persona = {}
            self.glossary_list = []

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
                "score": scores[idx]
            })
        return results

    def build_system_prompt(self, user_message: str) -> tuple[str, list[dict]]:
        """
        페르소나 캐릭터 지침과 단어장, 대본 RAG를 조합해 시스템 프롬프트를 구성합니다.
        """
        tone = self.persona.get("tone", "자연스러운 대화 말투")
        relationship = self.persona.get("relationship", "화자와 청자의 깊은 유대 관계")
        situation = self.persona.get("situation", "상황극 배경 정보 없음")
        key_rules = self.persona.get("key_rules", [])

        # 1. 기본 캐릭터 성격/관계
        persona_guide = f"- 당신의 말투 및 어조: {tone}\n"
        persona_guide += f"- 당신(화자)과 사용자(청자)의 관계: {relationship}\n"
        persona_guide += f"- 상황극 배경 및 맥락: {situation}\n"
        
        if key_rules:
            rules_str = "\n".join([f"  * {rule}" for rule in key_rules])
            persona_guide += f"- 연기 규칙:\n{rules_str}\n"

        # 2. 용어집 룰 추가
        glossary_guide = ""
        valid_glossaries = [g for g in self.glossary_list if g.get("원어 (Source)") and g.get("번역어 (Target)")]
        if valid_glossaries:
            glossary_guide = "\n<glossary>\n"
            for item in valid_glossaries:
                src = item["원어 (Source)"].strip()
                tgt = item["번역어 (Target)"].strip()
                ctx = item.get("설명/뉘앙스 (Context)", "").strip()
                ctx_str = f" ({ctx})" if ctx else ""
                glossary_guide += f"  - 단어 '{src}'를 사용할 때는 상황에 어울리게 고정어 '{tgt}' 혹은 어투에 맞게 표현하세요.{ctx_str}\n"
            glossary_guide += "</glossary>\n"

        # 3. RAG 대본 매칭 구절 (Hidden Hint)
        rag_hits = self.search_rag(user_message, top_n=3)
        rag_guide = ""
        if rag_hits:
            rag_guide = "\n[Hidden Hint: 당시 원작 대본에서 연기했던 씬 내용입니다. 대화 흐름상 적절히 인용하거나 참고하세요]\n"
            for hit in rag_hits:
                rag_guide += f"  - (원문 대사) {hit['original']} => (번역 대사) {hit['translated']}\n"
            rag_guide += "\n"

        system_prompt = f"""당신은 ASMR 상황극 및 대본 속 주인공 캐릭터입니다. 
주어진 캐릭터 가이드라인과 힌트를 완벽히 몸에 체화하여 사용자와 실시간 대화(롤플레잉)를 이어가세요.

[캐릭터 연기 가이드라인]
{persona_guide}
{glossary_guide}
{rag_guide}
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

        from mlx_vlm.generate import stream_generate
        from mlx_vlm.prompt_utils import apply_chat_template

        # 시스템 프롬프트 및 RAG 계산
        system_prompt, rag_hits = self.build_system_prompt(user_message)

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
            formatted_prompt = apply_chat_template(
                self.processor,
                self.model.config,
                messages,
                num_images=0,
                num_audios=0
            )

            generator = stream_generate(
                self.model,
                self.processor,
                prompt=formatted_prompt,
                temp=temp,
                max_tokens=1000,
                kv_bits=3.5,
                kv_quant_scheme="turboquant",
                repetition_penalty=repetition_penalty,
                repetition_context_size=100,
                seed=42,
            )

            # 3. 토큰 실시간 전송
            for response in generator:
                yield json.dumps({"event": "token", "data": response.text}, ensure_ascii=False) + "\n"

        except Exception as e:
            yield json.dumps({"event": "error", "data": str(e)}, ensure_ascii=False) + "\n"
        finally:
            import mlx.core as mx
            import gc
            mx.clear_cache()
            gc.collect()
