// Use centralized API from api-utils.js if available, otherwise fallback to production URL
const API_BASE = window.API || "https://exam-mate-backend-w5t6.onrender.com/api";

document.addEventListener("DOMContentLoaded", () => {
    // 1. Navigation Mapping
    // Find generic buttons by their text
    document.querySelectorAll("button, div.group, header span").forEach(el => {
        const text = el.innerText.toLowerCase().trim();
        if (text === "home") {
            el.onclick = () => window.location.href = "../dashboard_exam_mate/code.html";
            el.style.cursor = "pointer";
        }
        if (text.includes("upload") && !window.location.pathname.includes("upload_document_exam_mate")) {
            el.onclick = () => window.location.href = "../upload_document_exam_mate/code.html";
            el.style.cursor = "pointer";
        }
        if ((text.includes("ask question") || text.includes("start chat")) && !window.location.pathname.includes("ask_question_exam_mate")) {
            el.onclick = () => window.location.href = "../ask_question_exam_mate/code.html";
            el.style.cursor = "pointer";
        }
        if (text.includes("history") && !window.location.pathname.includes("history_exam_mate")) {
            el.onclick = () => window.location.href = "../history_exam_mate/code.html";
            el.style.cursor = "pointer";
        }
    });

    // 2. Upload Logic (If on Upload Page)
    if (window.location.pathname.includes("upload")) {
        const uploadArea = document.querySelector('label') || document.querySelector('.border-dashed');
        if (uploadArea) {
            // Create hidden file input
            const fileIn = document.createElement("input");
            fileIn.type = "file";
            fileIn.style.display = "none";
            document.body.appendChild(fileIn);

            uploadArea.onclick = (e) => {
                e.preventDefault();
                fileIn.click();
            };

            fileIn.onchange = async (e) => {
                const file = e.target.files[0];
                if (!file) return;
                
                alert("Uploading PDF to AI Backend...");
                const formData = new FormData();
                formData.append('file', file);
                
                try {
                    const res = await fetch(`${API_BASE}/upload`, { method: "POST", body: formData });
                    const data = await res.json().catch(() => ({}));
                    if (!res.ok) {
                        alert(data.error || "Backend Upload Error. Check server visibility.");
                        return;
                    }
                    if (data.document_id) {
                        sessionStorage.setItem("document_id", data.document_id);
                    }
                    alert("PDF processed by AI! Moving to Ask Screen...");
                    window.location.href = "../ask_question_exam_mate/code.html";
                } catch (err) {
                    alert("Backend Upload Error. Check server visibility.");
                }
            };
        }
    }

    // 3. Ask Logic (If on Ask Page)
    if (window.location.pathname.includes("ask")) {
        const chatInput = document.querySelector('input[type="text"]');
        const sendBtn = document.querySelectorAll('button')[1] || document.querySelector('span[data-icon="send"]')?.closest('button');
        
        if (chatInput && sendBtn) {
            sendBtn.onclick = async (e) => {
                e.preventDefault();
                const question = chatInput.value;
                if (!question) return;
                
                alert(`Asking Groq AI: ${question}...`);
                const payload = {
                    question: question,
                    document_id: sessionStorage.getItem("document_id") || undefined,
                    mode: "detailed"
                };
                const res = await fetch(`${API_BASE}/ask`, {
                    method: "POST", 
                    headers: { "Content-Type": "application/json" },
                    body: JSON.stringify(payload)
                });
                const data = await res.json().catch(() => ({}));
                if (!res.ok) {
                    alert(data.error || "Backend error. Check server logs.");
                    return;
                }
                const explanation = data.answer && data.answer.explanation ? data.answer.explanation : "";
                const points = Array.isArray(data.answer && data.answer.points)
                    ? data.answer.points.join("\n")
                    : "";
                const responseText = [explanation, points].filter(Boolean).join("\n");
                alert(`AI Replied:\n${responseText || "No answer returned."}`);
            };
        }
    }
});
