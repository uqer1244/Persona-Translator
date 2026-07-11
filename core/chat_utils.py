import math
import re

def clean_and_tokenize(text: str) -> list[str]:
    """
    텍스트에서 특수문자, 괄호 등을 제거하고 공백 단위로 쪼개어 토큰 리스트를 반환합니다.
    """
    # 괄호 및 문장부호 제거
    cleaned = re.sub(r'[\[\]\(\)\*\{\}\-\:\,\.\?\"\'\！\？\［\］\（\）\<\>\/]', ' ', text)
    # 공백 단위로 쪼개고 소문자화
    tokens = [w.strip().lower() for w in cleaned.split() if w.strip()]
    return tokens


class BM25Okapi:
    """
    순수 파이썬으로 구현된 BM25Okapi 알고리즘 클래스
    """
    def __init__(self, corpus: list[list[str]], k1: float = 1.5, b: float = 0.75):
        self.corpus_size = len(corpus)
        self.avgdl = sum(len(doc) for doc in corpus) / self.corpus_size if self.corpus_size > 0 else 0
        self.corpus = corpus
        self.k1 = k1
        self.b = b
        self.doc_freqs = []
        self.idf = {}
        self.doc_len = [len(doc) for doc in corpus]
        self._initialize()

    def _initialize(self):
        nd = {}  # term -> number of docs containing term
        for doc in self.corpus:
            frequencies = {}
            for word in doc:
                frequencies[word] = frequencies.get(word, 0) + 1
            self.doc_freqs.append(frequencies)
            for word in frequencies:
                nd[word] = nd.get(word, 0) + 1

        for word, freq in nd.items():
            # BM25 IDF 계산
            self.idf[word] = math.log(1 + (self.corpus_size - freq + 0.5) / (freq + 0.5))

    def get_scores(self, query_tokens: list[str]) -> list[float]:
        scores = [0.0] * self.corpus_size
        for i in range(self.corpus_size):
            doc_len = self.doc_len[i]
            if doc_len == 0:
                continue
            frequencies = self.doc_freqs[i]
            score = 0.0
            for word in query_tokens:
                if word in frequencies:
                    freq = frequencies[word]
                    idf = self.idf.get(word, 0)
                    # BM25 점수 공식
                    numerator = freq * (self.k1 + 1)
                    denominator = freq + self.k1 * (1 - self.b + self.b * (doc_len / self.avgdl))
                    score += idf * (numerator / denominator)
            scores[i] = score
        return scores


def build_rag_corpus(progress_data: dict) -> list[dict]:
    """
    progress_data의 original_chunks와 translated_chunks로부터 
    RAG 검색용 라인 단위의 코퍼스 리스트를 생성합니다.
    번역본이 없는 경우 원문 대사로 대체하여 작동하도록 구성합니다.
    """
    translated_chunks = progress_data.get("translated_chunks", [])
    original_chunks = progress_data.get("original_chunks", [])
    
    rag_items = []
    
    for chunk_idx, orig_chunk in enumerate(original_chunks):
        if not orig_chunk:
            continue
            
        trans_chunk = translated_chunks[chunk_idx] if chunk_idx < len(translated_chunks) else ""
        
        orig_lines = orig_chunk.split("\n")
        trans_lines = trans_chunk.split("\n") if trans_chunk else []
        
        for line_idx, o_line in enumerate(orig_lines):
            o_line_stripped = o_line.strip()
            if not o_line_stripped:
                continue
                
            # SRT 자막 포맷 무시 (타임코드 및 인덱스라인 제외)
            if re.match(r'^\d+$', o_line_stripped):
                continue
            if "-->" in o_line_stripped:
                continue
                
            t_line = trans_lines[line_idx].strip() if line_idx < len(trans_lines) else ""
            
            # 검색 매칭용 텍스트 (번역문 우선, 없으면 원문 사용)
            search_text = t_line if t_line else o_line_stripped
            
            tokens = clean_and_tokenize(search_text)
            if not tokens:
                continue
                
            rag_items.append({
                "chunk_index": chunk_idx,
                "line_index": line_idx,
                "original": o_line_stripped,
                "translated": t_line if t_line else o_line_stripped,
                "tokens": tokens
            })
            
    return rag_items


def summarize_chat_history(model, processor, history_list: list[dict], model_path: str) -> str:
    """
    VLM을 사용해 장기 대화 내역을 한 줄 요약본으로 압축합니다.
    """
    if not history_list:
        return ""
        
    formatted_dialogue = ""
    for turn in history_list:
        role_name = "사용자" if turn["role"] == "user" else "AI 캐릭터"
        formatted_dialogue += f"{role_name}: {turn['content']}\n"
        
    prompt = f"""다음은 사용자와 AI 캐릭터 간의 ASMR 상황극 대화 내역입니다. 
이 대화 내역을 바탕으로 두 사람이 지금까지 나눈 핵심 이야기 흐름과 상황을 '한 줄의 요약문'으로 만들어 주세요. 
답변은 오직 요약문만 간결하게 출력하세요. 다른 잡담은 일절 배제하십시오.

[대화 내역]
{formatted_dialogue}

[한 줄 요약]"""

    try:
        from mlx_vlm.utils import generate
        # mlx_vlm을 사용한 동기식 요약 텍스트 생성
        messages = [{"role": "user", "content": [{"type": "text", "text": prompt}]}]
        
        # apply_chat_template을 사용하여 프롬프트 변환
        prompt_templated = processor.apply_chat_template(messages, add_generation_prompt=True)
        
        response = generate(
            model=model,
            processor=processor,
            prompt=prompt_templated,
            max_tokens=150,
            verbose=False
        )
        return response.strip()
    except Exception as e:
        print(f"Failed to summarize history: {e}")
        # 오류 시 간단히 최근 대사 일부를 그냥 요약 대신 리턴
        return "과거 대화 요약 생성에 실패했습니다."
