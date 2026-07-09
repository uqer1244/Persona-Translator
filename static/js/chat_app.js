// chat_app.js
document.addEventListener("DOMContentLoaded", () => {
    // DOM Elements
    const projectSelect = document.getElementById("project-select");
    const modelSelect = document.getElementById("model-select");
    const loadBtn = document.getElementById("load-btn");
    const unloadBtn = document.getElementById("unload-btn");
    const chatInput = document.getElementById("chat-input");
    const sendBtn = document.getElementById("send-btn");
    const resetBtn = document.getElementById("reset-btn");
    const chatMessages = document.getElementById("chat-messages");
    
    // Cards
    const personaCard = document.getElementById("persona-card");
    const personaRelation = document.getElementById("persona-relation");
    const personaTone = document.getElementById("persona-tone");
    const personaSituation = document.getElementById("persona-situation");
    
    const glossaryCard = document.getElementById("glossary-card");
    const glossaryList = document.getElementById("glossary-list");
    
    // Header & Status Info
    const currentProjectTitle = document.getElementById("current-project-title");
    const currentModelInfo = document.getElementById("current-model-info");
    const statusDot = document.getElementById("status-dot");
    const statusText = document.getElementById("status-text");
    
    // RAG Hint Panel
    const hintPanel = document.getElementById("hint-panel");
    const hintContent = document.getElementById("hint-content");

    // Chat Memory
    let chatHistory = [];
    let isGenerating = false;

    // Initialization: Fetch project list & model list
    async function init() {
        try {
            updateStatus("loading", "기본 정보 로드 중...");
            
            // 1. Projects API
            const projectsRes = await fetch("/api/projects");
            const projectsData = await projectsRes.json();
            if (projectsData.projects) {
                projectsData.projects.forEach(proj => {
                    const opt = document.createElement("option");
                    opt.value = proj;
                    opt.textContent = proj;
                    projectSelect.appendChild(opt);
                });
            }
            
            // 2. Models API
            const modelsRes = await fetch("/api/models");
            const modelsData = await modelsRes.json();
            if (modelsData.models) {
                modelsData.models.forEach(modelPath => {
                    const opt = document.createElement("option");
                    opt.value = modelPath;
                    // 폴더 끝 이름만 보여주어 간략화
                    const folderName = modelPath.split("/").pop();
                    opt.textContent = folderName;
                    modelSelect.appendChild(opt);
                });
            }
            
            updateStatus("idle", "연결 대기중");
        } catch (e) {
            console.error("Init failure:", e);
            updateStatus("error", "연결 실패");
            alert("서버 연결에 실패했습니다. FastAPI가 켜져 있는지 확인하세요.");
        }
    }

    // Helper to change UI status indicators
    function updateStatus(state, message) {
        statusDot.className = "status-dot";
        statusText.textContent = message;
        
        if (state === "active") {
            statusDot.classList.add("active");
        } else if (state === "loading") {
            statusDot.classList.add("loading");
        } else if (state === "error") {
            // Error state logic can be added
        }
    }

    // Render ASMR Format (Bracket Highlight)
    function formatAsmrResponse(text) {
        if (!text) return "";
        // [...] or ［...］ brackets highlighted with action-tag
        return text.replace(/(\[.*?\]|［.*?］)/g, '<span class="action-tag">$1</span>');
    }

    // Append Message to UI
    function appendMessage(role, text, isSystem = false) {
        const msgDiv = document.createElement("div");
        msgDiv.className = `message ${role}`;
        
        const bubble = document.createElement("div");
        bubble.className = "message-bubble";
        if (role === "assistant" && !isSystem) {
            bubble.innerHTML = formatAsmrResponse(text);
        } else {
            bubble.textContent = text;
        }
        
        const meta = document.createElement("div");
        meta.className = "message-meta";
        meta.textContent = isSystem ? "System" : (role === "user" ? "You" : "Character");
        
        msgDiv.appendChild(bubble);
        msgDiv.appendChild(meta);
        chatMessages.appendChild(msgDiv);
        
        chatMessages.scrollTop = chatMessages.scrollHeight;
        return bubble;
    }

    // Show/Hide RAG Hint Panel
    function showRagHits(hits) {
        if (!hits || hits.length === 0) {
            hintPanel.style.display = "none";
            return;
        }
        
        hintContent.innerHTML = "";
        hits.forEach(hit => {
            const hitItem = document.createElement("div");
            hitItem.className = "hint-item";
            
            const orig = document.createElement("div");
            orig.textContent = `原: ${hit.original}`;
            
            const trans = document.createElement("div");
            trans.className = "hint-translated";
            trans.textContent = `譯: ${hit.translated}`;
            
            hitItem.appendChild(orig);
            hitItem.appendChild(trans);
            hintContent.appendChild(hitItem);
        });
        
        hintPanel.style.display = "block";
    }

    // Load Project & Model Click Event
    loadBtn.addEventListener("click", async () => {
        const selectedProj = projectSelect.value;
        const selectedModel = modelSelect.value;
        
        if (!selectedProj) {
            alert("대화할 대상 프로젝트를 선택하세요.");
            return;
        }
        
        try {
            loadBtn.disabled = true;
            unloadBtn.disabled = true;
            updateStatus("loading", "VLM 모델 메모리 적재 중 (최대 1분 소요)...");
            
            const res = await fetch("/api/projects/load", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({
                    project_name: selectedProj,
                    model_path: selectedModel
                })
            });
            
            const data = await res.json();
            if (res.status === 200) {
                // UI Enable
                chatInput.disabled = false;
                sendBtn.disabled = false;
                
                // Show Cards
                renderPersonaCard(data.persona);
                renderGlossaryCard(data.glossary);
                
                // Header Info update
                currentProjectTitle.textContent = selectedProj;
                currentModelInfo.textContent = selectedModel ? selectedModel.split("/").pop() : "기본 VLM 모델";
                
                // Welcome Message
                chatMessages.innerHTML = "";
                appendMessage("assistant", "대본 페르소나 적재 완료! 대화를 시작하면 대본을 RAG 검색하여 롤플레잉이 진행됩니다. [기대 섞인 표정으로 쳐다본다]", true);
                chatHistory = [];
                
                updateStatus("active", "대화 엔진 가동 중 (VRAM 로드 완료)");
            } else {
                throw new Error(data.detail || "Unknown error occurred.");
            }
        } catch (e) {
            console.error(e);
            alert("프로젝트 로딩 실패: " + e.message);
            updateStatus("idle", "로드 실패");
        } finally {
            loadBtn.disabled = false;
            unloadBtn.disabled = false;
        }
    });

    // Unload Model Click Event
    unloadBtn.addEventListener("click", async () => {
        try {
            updateStatus("loading", "모델 VRAM 회수 중...");
            const res = await fetch("/api/chat/unload", { method: "POST" });
            const data = await res.json();
            
            if (res.status === 200) {
                chatInput.disabled = true;
                sendBtn.disabled = true;
                updateStatus("idle", "연결 대기중 (VRAM 해제됨)");
                appendMessage("assistant", "모델이 VRAM에서 해제되었습니다. 대화를 재개하려면 프로젝트를 다시 로드하세요.", true);
            }
        } catch (e) {
            console.error(e);
            alert("언로드 실패: " + e.message);
        }
    });

    // Render Cards Helpers
    function renderPersonaCard(persona) {
        if (!persona) {
            personaCard.style.display = "none";
            return;
        }
        
        personaRelation.textContent = persona.relationship || "설정 없음";
        personaTone.textContent = persona.tone || "설정 없음";
        personaSituation.textContent = persona.situation || "배경 설명 없음";
        personaCard.style.display = "flex";
    }

    function renderGlossaryCard(glossary) {
        glossaryList.innerHTML = "";
        if (!glossary || glossary.length === 0) {
            glossaryCard.style.display = "none";
            return;
        }
        
        glossary.forEach(item => {
            const row = document.createElement("div");
            row.style.borderBottom = "1px solid rgba(255, 255, 255, 0.03)";
            row.style.paddingBottom = "4px";
            
            const pair = document.createElement("strong");
            pair.style.color = "var(--text-primary)";
            pair.textContent = `${item["원어 (Source)"]} → ${item["번역어 (Target)"]}`;
            
            const desc = document.createElement("div");
            desc.style.fontSize = "11px";
            desc.textContent = item["설명/뉘앙스 (Context)"] || "";
            
            row.appendChild(pair);
            if (item["설명/뉘앙스 (Context)"]) {
                row.appendChild(desc);
            }
            glossaryList.appendChild(row);
        });
        
        glossaryCard.style.display = "flex";
    }

    // Send Message Logic
    async function sendMessage() {
        const text = chatInput.value.trim();
        if (!text || isGenerating) return;
        
        // UI lock
        chatInput.value = "";
        chatInput.disabled = true;
        sendBtn.disabled = true;
        isGenerating = true;
        
        // 1. User Message Append
        appendMessage("user", text);
        
        // Placeholder for Assistant Streaming bubble
        const assistantBubble = appendMessage("assistant", "");
        
        try {
            updateStatus("loading", "AI 답변 작성 중...");
            
            // 2. Fetch SSE stream using fetch API (for safe long URL query string)
            const queryParams = new URLSearchParams({
                user_message: text,
                history: JSON.stringify(chatHistory)
            });
            
            const response = await fetch(`/api/chat/stream?${queryParams.toString()}`);
            if (!response.ok) {
                const errData = await response.json();
                throw new Error(errData.detail || "Stream error");
            }
            
            const reader = response.body.getReader();
            const decoder = new TextDecoder();
            
            let buffer = "";
            let fullAiResponse = "";
            
            while (true) {
                const { done, value } = await reader.read();
                if (done) break;
                
                buffer += decoder.decode(value, { stream: true });
                const lines = buffer.split("\n");
                
                // 마지막 완성 안 된 줄은 버퍼에 보존
                buffer = lines.pop();
                
                for (const line of lines) {
                    const cleanLine = line.trim();
                    if (cleanLine.startsWith("data: ")) {
                        const jsonStr = cleanLine.substring(6).trim();
                        if (!jsonStr) continue;
                        
                        try {
                            const payload = JSON.parse(jsonStr);
                            
                            // Event handling
                            if (payload.event === "rag_hits") {
                                showRagHits(payload.data);
                            } else if (payload.event === "token") {
                                fullAiResponse += payload.data;
                                assistantBubble.innerHTML = formatAsmrResponse(fullAiResponse);
                                chatMessages.scrollTop = chatMessages.scrollHeight;
                            } else if (payload.event === "error") {
                                throw new Error(payload.data);
                            }
                        } catch (err) {
                            console.error("JSON parse error on stream line:", err);
                        }
                    }
                }
            }
            
            // 3. Update Chat History
            chatHistory.push({ role: "user", content: text });
            chatHistory.push({ role: "assistant", content: fullAiResponse });
            
            // 대화 기록 누적으로 인한 무거운 메모리 압축 방지차 최대 12턴 유지 (단기 메모리 슬라이딩)
            if (chatHistory.length > 20) {
                chatHistory = chatHistory.slice(-20);
            }
            
            updateStatus("active", "대화 엔진 가동 중 (VRAM 로드 완료)");
        } catch (e) {
            console.error(e);
            assistantBubble.innerHTML = `<span class="error-bubble">[오류 발생: ${e.message}]</span>`;
            updateStatus("active", "대화 중 오류 발생");
        } finally {
            chatInput.disabled = false;
            sendBtn.disabled = false;
            chatInput.focus();
            isGenerating = false;
        }
    }

    // Input Box Trigger Send
    sendBtn.addEventListener("click", sendMessage);
    chatInput.addEventListener("keydown", (e) => {
        if (e.key === "Enter" && !e.shiftKey) {
            e.preventDefault();
            sendMessage();
        }
    });

    // Reset Chat Trigger
    resetBtn.addEventListener("click", () => {
        if (confirm("현재 상황극 대화 내역을 모두 지우시겠습니까?")) {
            chatHistory = [];
            chatMessages.innerHTML = "";
            appendMessage("assistant", "상황극 대화 기록이 초기화되었습니다. [기지개를 켜며 가벼운 미소를 짓는다]", true);
            hintPanel.style.display = "none";
        }
    });

    // Kickoff UI initialization
    init();
});
