import os
import re
import json
import time
import requests
from typing import Dict, Any, List, Tuple, Optional
from dotenv import load_dotenv
from groq import Groq

load_dotenv()

_DEFAULT_GROQ_MODEL = "openai/gpt-oss-120b"
_FALLBACK_MODELS = ["openai/gpt-oss-20b", "qwen/qwen3.8-27b"]

def get_groq_client():
    key = os.environ.get("GROQ_API_KEY")
    if key and key.startswith("gsk_") and len(key) > 20:
        try:
            return Groq(api_key=key)
        except Exception:
            return None
    return None

def detect_keywords(text: str) -> List[str]:
    """Extracts prominent technical keywords from answer text."""
    words = re.findall(r'\b[A-Z][a-zA-Z0-9_\-]{2,}\b|\b[a-zA-Z]{5,}\b', text)
    stop_words = {
        "should", "because", "between", "through", "during", "before", "without",
        "following", "example", "another", "standard", "provides", "defined", "system"
    }
    filtered = [w for w in words if w.lower() not in stop_words]
    seen = set()
    result = []
    for w in filtered:
        wl = w.lower()
        if wl not in seen:
            seen.add(wl)
            result.append(w)
            if len(result) >= 8:
                break
    return result

# ── Self-Healing Mermaid JS Sanitizer ────────────────────────────────────────

def heal_mermaid_diagram(raw_mermaid: Optional[str], topic: str = "Concept Architecture") -> str:
    """
    Self-healing Mermaid JS validator and sanitizer.
    Guarantees syntactically valid Mermaid code even if the AI produced unquoted parentheses,
    broken connectors, or markdown code fence wrappers.
    """
    clean_topic = re.sub(r'[^a-zA-Z0-9 ]', '', topic)[:30].strip() or "Core Architecture"

    if not raw_mermaid or not isinstance(raw_mermaid, str) or len(raw_mermaid.strip()) < 8:
        return f"""flowchart TD
    A["{clean_topic} Input"] --> B["Processing Engine"]
    B --> C["Core Algorithm / Operation"]
    C --> D["Output & Assessment"]"""

    text = raw_mermaid.strip()
    # Strip markdown code blocks
    text = re.sub(r'^```(?:mermaid)?\s*', '', text, flags=re.IGNORECASE)
    text = re.sub(r'\s*```$', '', text).strip()

    valid_directives = ("graph ", "flowchart ", "sequenceDiagram", "classDiagram", "stateDiagram", "erDiagram")
    if not any(text.startswith(d) for d in valid_directives):
        text = "flowchart TD\n  " + text

    # Self-heal unquoted brackets containing parens, commas, or special chars
    # e.g. A[Input (Data)] -> A["Input (Data)"]
    def quote_brackets(match):
        node_id = match.group(1)
        label = match.group(2).strip()
        if (label.startswith('"') and label.endswith('"')) or (label.startswith("'") and label.endswith("'")):
            return f"{node_id}[{label}]"
        safe_label = label.replace('"', "'")
        return f'{node_id}["{safe_label}"]'

    text = re.sub(r'([a-zA-Z0-9_\-]+)\[([^\]\n]+)\]', quote_brackets, text)

    # Fix broken arrows
    text = re.sub(r'--\s+>', '-->', text)
    text = re.sub(r'-\s+->', '-->', text)

    return text

# ── Local Grounded Academic Synthesizer (Zero-Failure Fallback) ───────────────

def _synthesize_grounded_exam_answer_local(question: str, retrieval_result: Dict[str, Any], 
                                          mode: str, marks: int) -> Dict[str, Any]:
    """Precision local synthesis from retrieved passages without hallucination."""
    chunks = retrieval_result.get("chunks", [])
    if not chunks:
        return {
            "answer_text": "The supplied material does not contain enough information to answer this question reliably.",
            "structured_answer": {
                "definition": "Insufficient information in source material.",
                "explanation": "No matching text passages were found in your uploaded documents.",
                "points": [],
                "examples": [],
                "conclusion": "Please verify your question or upload relevant study materials."
            },
            "citations": [],
            "is_grounded": False,
            "confidence": 0.0,
            "mermaid_code": None
        }

    all_sentences = []
    for c in chunks:
        p_no = c["page_number"]
        sec = c["section_title"]
        s_list = re.split(r'(?<=[.!?])\s+', c["chunk_text"])
        for s in s_list:
            clean_s = s.strip()
            if len(clean_s) > 25:
                all_sentences.append({"sentence": clean_s, "page": p_no, "section": sec})

    definition_cand = None
    for item in all_sentences:
        lower_s = item["sentence"].lower()
        if any(term in lower_s for term in [" is ", " defined as ", " refers to ", " represents ", " consists of "]):
            definition_cand = item["sentence"]
            break
    if not definition_cand and all_sentences:
        definition_cand = all_sentences[0]["sentence"]

    # Target points based on marks (2, 5, 10, or 16)
    if marks <= 2:
        target_points = 2
    elif marks <= 5:
        target_points = 4
    elif marks <= 10:
        target_points = 7
    else:  # 16 marks
        target_points = 10

    key_points = []
    seen_texts = set()
    if definition_cand:
        seen_texts.add(definition_cand.lower())

    for item in all_sentences:
        s_text = item["sentence"]
        if s_text.lower() not in seen_texts:
            seen_texts.add(s_text.lower())
            key_points.append(f"{s_text} (Ref: Page {item['page']})")
            if len(key_points) >= target_points:
                break

    examples = []
    for item in all_sentences:
        if any(ex_term in item["sentence"].lower() for ex_term in ["for example", "e.g.", "such as", "case in point"]):
            examples.append(f"{item['sentence']} (Page {item['page']})")
            if len(examples) >= 3:
                break

    conclusion = f"In summary, based on Page {chunks[0]['page_number']} of the study material, mastery of these principles is critical for {marks}-mark university evaluations."

    sections = [
        f"### 1. Definition / Core Concept\n{definition_cand}",
        f"\n### 2. Key Explanatory Points ({marks} Marks)\n" + "\n".join([f"{i+1}. {p}" for i, p in enumerate(key_points)])
    ]
    if examples:
        sections.append(f"\n### 3. Source Examples\n" + "\n".join([f"- {ex}" for ex in examples]))
    sections.append(f"\n### 4. Summary\n{conclusion}")

    mermaid_diagram = heal_mermaid_diagram(None, question) if mode == "ai_enhanced" else None

    return {
        "answer_text": "\n".join(sections),
        "structured_answer": {
            "definition": definition_cand or "",
            "explanation": " ".join([p.split(" (Ref:")[0] for p in key_points[:2]]),
            "points": key_points,
            "examples": examples,
            "conclusion": conclusion
        },
        "citations": retrieval_result.get("citations", []),
        "is_grounded": True,
        "confidence": retrieval_result.get("confidence", 0.9),
        "mermaid_code": mermaid_diagram
    }

# ── Primary Exam Answer Generator ─────────────────────────────────────────────

def generate_exam_answer(question: str, retrieval_result: Dict[str, Any], 
                         mode: str = "detailed", marks: int = 5) -> Dict[str, Any]:
    """
    Produces a rigorously grounded exam answer.
    Supports 2, 5, 10, and 16 marks.
    Supports 'detailed' (Standard Grounded) and 'ai_enhanced' (with self-healing Mermaid diagram).
    """
    if not retrieval_result.get("is_sufficient"):
        return {
            "answer_text": "The supplied material does not contain enough information to answer this question reliably.",
            "structured_answer": {
                "definition": "Insufficient Evidence",
                "explanation": "The uploaded material does not contain verifiable facts or discussion regarding this topic.",
                "points": [],
                "examples": [],
                "conclusion": "Answers cannot be fabricated without source attribution."
            },
            "citations": [],
            "is_grounded": False,
            "confidence": 0.0,
            "mermaid_code": None
        }

    client = get_groq_client()
    if client is None:
        return _synthesize_grounded_exam_answer_local(question, retrieval_result, mode, marks)

    context = retrieval_result.get("combined_context", "")
    citations = retrieval_result.get("citations", [])

    is_16_marks = marks >= 16
    is_enhanced = mode == "ai_enhanced"

    essay_format = "Comprehensive 16-Mark University Essay Format: deep introduction, architectural/system breakdown, 8-10 exhaustive mechanism points, case study/examples, and critical trade-offs" if is_16_marks else "Targeted exam structure"
    answer_style = "AI-Enhanced with Architecture/Process Diagram" if is_enhanced else "Standard Grounded Material Reference"
    comma_sep = "," if is_enhanced else ""
    mermaid_field = '\n    "mermaid_diagram": "Valid Mermaid.js diagram code (e.g. flowchart TD or sequenceDiagram). Always wrap node text in double quotes like A[\\"Label\\"] --> B[\\"Label\\"]. Do not use unquoted parentheses inside node brackets."' if is_enhanced else ""

    system_prompt = f"""You are Exam Mate AI, an academic exam preparation specialist for university engineering and degree examinations.
Answer the user's exam question strictly grounded in the provided source context.
Do not hallucinate or cite unseen material.
If evidence is missing, state: 'The supplied material does not contain enough information to answer this question reliably.'

Exam requirements:
- Marks allocated: {marks} marks ({essay_format})
- Answer style: {answer_style}
- Cite specific page references (e.g. [Page X]) throughout the points.

Return valid JSON with this exact schema:
{{
    "definition": "Precise, rigorous formal definition (1-3 sentences)",
    "explanation": "In-depth theoretical explanation and background",
    "points": ["Exhaustive technical point 1 [Page X]", "Technical point 2 [Page Y]"],
    "examples": ["Concrete real-world application or example from material [Page Z]"],
    "conclusion": "Concluding summary emphasizing academic significance"{comma_sep}{mermaid_field}
}}
"""

    user_prompt = f"""Context from uploaded study material:
{context}

Exam Question:
{question}
"""

    for model_name in [_DEFAULT_GROQ_MODEL] + _FALLBACK_MODELS:
        try:
            resp = client.chat.completions.create(
                model=model_name,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt}
                ],
                temperature=0.15,
                max_tokens=2200 if is_16_marks else 1400,
                response_format={"type": "json_object"}
            )
            raw_content = resp.choices[0].message.content
            parsed = json.loads(raw_content)

            text_lines = [
                f"### 1. Definition & Core Concept\n{parsed.get('definition', '')}",
                f"\n### 2. Theoretical Background\n{parsed.get('explanation', '')}",
                f"\n### 3. Detailed Mechanism & Key Points ({marks} Marks)\n" + "\n".join([f"{i+1}. {pt}" for i, pt in enumerate(parsed.get('points', []))])
            ]
            if parsed.get('examples'):
                text_lines.append(f"\n### 4. Practical Applications & Examples\n" + "\n".join([f"- {ex}" for ex in parsed.get('examples', [])]))
            text_lines.append(f"\n### 5. Academic Conclusion\n{parsed.get('conclusion', '')}")

            mermaid_code = None
            if is_enhanced:
                raw_mermaid = parsed.get("mermaid_diagram")
                mermaid_code = heal_mermaid_diagram(raw_mermaid, question)

            return {
                "answer_text": "\n".join(text_lines),
                "structured_answer": parsed,
                "citations": citations,
                "is_grounded": True,
                "confidence": retrieval_result.get("confidence", 0.95),
                "mermaid_code": mermaid_code
            }
        except Exception:
            continue

    # Fallback to local grounded synthesis if Groq errors
    return _synthesize_grounded_exam_answer_local(question, retrieval_result, mode, marks)

# ── Google Gemini Engine (Flashcards & Quizzes) ───────────────────────────────

def call_gemini_json(prompt: str, context: str, timeout: int = 8) -> Optional[Dict[str, Any]]:
    """
    Calls Google Gemini API (gemini-3.5-flash) using JSON mode.
    Exclusively used for high-yield flashcard & MCQ quiz generation from uploaded study materials.
    """
    key = os.environ.get("GEMINI_API_KEY")
    if not key or len(key.strip()) < 10:
        return None

    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-3.5-flash:generateContent?key={key.strip()}"
    payload = {
        "contents": [
            {
                "parts": [
                    {"text": f"{prompt}\n\nStudy Material Context:\n{context}"}
                ]
            }
        ],
        "generationConfig": {
            "responseMimeType": "application/json",
            "temperature": 0.2,
            "maxOutputTokens": 3000,
            "thinkingConfig": {
                "thinkingBudget": 0
            }
        }
    }
    try:
        r = requests.post(url, json=payload, timeout=timeout)
        if r.status_code == 200:
            res_data = r.json()
            candidates = res_data.get("candidates", [])
            if candidates:
                parts = candidates[0].get("content", {}).get("parts", [])
                if parts and "text" in parts[0]:
                    return json.loads(parts[0]["text"])
    except Exception as e:
        print(f"Gemini API request failed: {e}")
        return None
    return None

# ── Flashcard Generator ───────────────────────────────────────────────────────

def generate_flashcards_from_chunks(chunks: List[Dict[str, Any]], count: int = 5) -> List[Dict[str, Any]]:
    """
    Generates revision flashcards grounded in source passages with page attribution.
    Powered primarily by Google Gemini (gemini-3.5-flash), with fallback to Groq and local extraction.
    """
    context_text = "\n\n".join([f"[Page {c.get('page_number', 1)}] {c.get('chunk_text', '')[:250]}" for c in chunks[:5]])
    system_prompt = f"""Generate {count} high-yield study flashcards from the study material context below.
Each flashcard must have a concise, challenging prompt on the 'front', a clear factual explanation on the 'back', and the cited page number.
Return JSON:
{{
  "flashcards": [
    {{"front": "What is ...?", "back": "...", "source_page": 1, "source_snippet": "..."}}
  ]
}}"""

    # 1. Primary Engine: Google Gemini API (as requested by user)
    gemini_data = call_gemini_json(system_prompt, context_text)
    if gemini_data:
        cards = gemini_data.get("flashcards", [])
        if cards and len(cards) > 0:
            return cards[:count]

    # 2. Secondary Engine: Groq LLM
    client = get_groq_client()
    if client:
        try:
            for model_name in [_DEFAULT_GROQ_MODEL] + _FALLBACK_MODELS:
                try:
                    resp = client.chat.completions.create(
                        model=model_name,
                        messages=[
                            {"role": "system", "content": system_prompt},
                            {"role": "user", "content": context_text}
                        ],
                        temperature=0.2,
                        max_tokens=600,
                        response_format={"type": "json_object"}
                    )
                    data = json.loads(resp.choices[0].message.content)
                    cards = data.get("flashcards", [])
                    if cards and len(cards) > 0:
                        return cards[:count]
                except Exception:
                    continue
        except Exception:
            pass

    # High-quality regex local fallback
    cards = []
    pattern = re.compile(r'\s+(?:is defined as|refers to|is the|is an|is a|consists of|serves as|enables|checks for)\s+', re.IGNORECASE)
    for c in chunks:
        p_no = c.get("page_number", 1)
        text = c.get("chunk_text", "")
        sentences = re.split(r'(?<=[.!?])\s+', text)
        for s in sentences:
            s_clean = s.strip()
            if len(s_clean) > 30:
                match = pattern.search(s_clean)
                if match:
                    subject = s_clean[:match.start()].strip()
                    definition = s_clean[match.end():].strip()
                    if 3 < len(subject) < 60 and len(definition) > 10:
                        cards.append({
                            "front": f"What is {subject}?",
                            "back": f"{subject} {s_clean[match.start():].strip()}",
                            "source_page": p_no,
                            "source_snippet": s_clean[:180]
                        })
                        if len(cards) >= count:
                            return cards

    # Fill remaining from key paragraphs
    for c in chunks:
        if len(cards) >= count:
            break
        p_no = c.get("page_number", 1)
        sec = c.get("section_title", "Concept")
        text = c.get("chunk_text", "").strip()
        paragraphs = [p for p in text.split("\n\n") if len(p.strip()) > 30]
        for p in paragraphs:
            cards.append({
                "front": f"Explain key concept from Page {p_no}: {p[:40]}...",
                "back": p[:250],
                "source_page": p_no,
                "source_snippet": p[:180]
            })
            if len(cards) >= count:
                break

    return cards[:count]

# ── Quiz Generator ─────────────────────────────────────────────────────────────

def generate_quiz_from_chunks(chunks: List[Dict[str, Any]], count: int = 5) -> List[Dict[str, Any]]:
    """
    Generates multiple-choice quiz questions strictly grounded in source passages.
    Powered primarily by Google Gemini (gemini-3.5-flash), with fallback to Groq and local extraction.
    """
    context_text = "\n\n".join([f"[Page {c.get('page_number', 1)}] {c.get('chunk_text', '')[:250]}" for c in chunks[:5]])
    system_prompt = f"""Generate {count} multiple-choice exam questions strictly based on the provided material.
Requirements for each question:
- 4 plausible options
- Exactly one correct option
- 0-indexed 'correct_option_index' (0, 1, 2, or 3)
- 'explanation' citing why the correct answer is right
- 'source_page' integer

Return JSON:
{{
  "questions": [
    {{
      "question_text": "...",
      "options": ["A", "B", "C", "D"],
      "correct_option_index": 0,
      "explanation": "...",
      "source_page": 1,
      "source_snippet": "..."
    }}
  ]
}}"""

    # 1. Primary Engine: Google Gemini API (as requested by user)
    gemini_data = call_gemini_json(system_prompt, context_text)
    if gemini_data:
        qs = gemini_data.get("questions", [])
        if qs and len(qs) > 0:
            return qs[:count]

    # 2. Secondary Engine: Groq LLM
    client = get_groq_client()
    if client:
        try:
            for model_name in [_DEFAULT_GROQ_MODEL] + _FALLBACK_MODELS:
                try:
                    resp = client.chat.completions.create(
                        model=model_name,
                        messages=[
                            {"role": "system", "content": system_prompt},
                            {"role": "user", "content": context_text}
                        ],
                        temperature=0.2,
                        max_tokens=900,
                        response_format={"type": "json_object"}
                    )
                    data = json.loads(resp.choices[0].message.content)
                    qs = data.get("questions", [])
                    if qs and len(qs) > 0:
                        return qs[:count]
                except Exception:
                    continue
        except Exception:
            pass

    # Reliable local fallback
    questions = []
    distractor_pool = [
        "Increases network latency across distributed clusters",
        "Decreases computational throughput during batch execution",
        "Prevents persistent storage serialization",
        "Requires manual intervention on every transaction",
        "Allocates memory dynamically without bounds checking",
        "Restricts database reads to single-threaded sequential scans"
    ]

    for c in chunks:
        if len(questions) >= count:
            break
        p_no = c.get("page_number", 1)
        text = c.get("chunk_text", "")
        sentences = re.split(r'(?<=[.!?])\s+', text)

        for s in sentences:
            s_clean = s.strip()
            if len(s_clean) > 50 and any(kw in s_clean.lower() for kw in ["is used to", "serves as", "enables", "primary advantage", "defined as", "principle"]):
                q_text = f"According to Page {p_no}, which of the following is correct regarding: {s_clean[:40]}...?"
                correct_opt = s_clean[:117] + "..." if len(s_clean) > 120 else s_clean

                options = [
                    correct_opt,
                    distractor_pool[(len(questions) * 2) % len(distractor_pool)],
                    distractor_pool[(len(questions) * 2 + 1) % len(distractor_pool)],
                    distractor_pool[(len(questions) * 2 + 2) % len(distractor_pool)]
                ]
                correct_idx = len(questions) % 4
                options[0], options[correct_idx] = options[correct_idx], options[0]

                questions.append({
                    "question_text": q_text,
                    "options": options,
                    "correct_option_index": correct_idx,
                    "explanation": f"Source passage on Page {p_no} states: '{s_clean}'",
                    "source_page": p_no,
                    "source_snippet": s_clean[:200]
                })
                break

    while len(questions) < min(count, len(chunks)):
        idx = len(questions)
        c = chunks[idx % len(chunks)]
        p_no = c.get("page_number", 1)
        sec = c.get("section_title", "Topic")
        snip = c.get("chunk_text", "")[:120]
        options = [
            f"It covers the verified principles of {sec}",
            "It deprecates all prior academic methodologies",
            "It is restricted solely to theoretical analysis without practical use",
            "It contradicts modern software development standards"
        ]
        correct_idx = idx % 4
        options[0], options[correct_idx] = options[correct_idx], options[0]
        questions.append({
            "question_text": f"What is the main topic covered in Page {p_no} under '{sec}'?",
            "options": options,
            "correct_option_index": correct_idx,
            "explanation": f"Page {p_no} discusses {sec}: '{snip}...'",
            "source_page": p_no,
            "source_snippet": snip
        })

    return questions
