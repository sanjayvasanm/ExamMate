import os
import re
import json
import time
from typing import Dict, Any, List, Tuple, Optional
from groq import Groq

GROQ_API_KEY = os.environ.get("GROQ_API_KEY")
_DEFAULT_GROQ_MODEL = "llama-3.3-70b-versatile"
_FALLBACK_MODELS = ["llama-3.1-8b-instant", "qwen/qwen3.6-27b"]

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
    # Return top 8 unique keywords
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

# ── Local Grounded Academic Synthesizer (Zero-Failure Fallback) ───────────────

def _synthesize_grounded_exam_answer_local(question: str, retrieval_result: Dict[str, Any], 
                                          mode: str, marks: int) -> Dict[str, Any]:
    """
    Precision local synthesis from retrieved passages:
    Directly extracts and structures facts from source chunks without hallucination.
    """
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
            "confidence": 0.0
        }

    # Extract sentences across retrieved chunks
    all_sentences = []
    for c in chunks:
        p_no = c["page_number"]
        sec = c["section_title"]
        s_list = re.split(r'(?<=[.!?])\s+', c["chunk_text"])
        for s in s_list:
            clean_s = s.strip()
            if len(clean_s) > 25:
                all_sentences.append({"sentence": clean_s, "page": p_no, "section": sec})

    # Pick definition (sentence containing 'is', 'defined as', 'refers to', or first sentence)
    definition_cand = None
    for item in all_sentences:
        lower_s = item["sentence"].lower()
        if any(term in lower_s for term in [" is ", " defined as ", " refers to ", " represents ", " consists of "]):
            definition_cand = item["sentence"]
            break
    if not definition_cand and all_sentences:
        definition_cand = all_sentences[0]["sentence"]

    # Pick key points
    target_points = 2 if marks <= 2 else (4 if marks <= 5 else 6)
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

    # Pick example if available
    examples = []
    for item in all_sentences:
        if any(ex_term in item["sentence"].lower() for ex_term in ["for example", "e.g.", "such as", "case in point"]):
            examples.append(f"{item['sentence']} (Page {item['page']})")
            if len(examples) >= 2:
                break

    conclusion = f"In summary, based on Page {chunks[0]['page_number']} of the study material, understanding these core principles is essential for {marks}-mark academic assessments."

    # Format answer text
    sections = [
        f"### 1. Definition / Core Concept\n{definition_cand}",
        f"\n### 2. Key Explanatory Points\n" + "\n".join([f"{i+1}. {p}" for i, p in enumerate(key_points)])
    ]
    if examples:
        sections.append(f"\n### 3. Source Examples\n" + "\n".join([f"- {ex}" for ex in examples]))
    sections.append(f"\n### 4. Summary\n{conclusion}")

    full_answer = "\n".join(sections)

    return {
        "answer_text": full_answer,
        "structured_answer": {
            "definition": definition_cand or "",
            "explanation": " ".join([p.split(" (Ref:")[0] for p in key_points[:2]]),
            "points": key_points,
            "examples": examples,
            "conclusion": conclusion
        },
        "citations": retrieval_result.get("citations", []),
        "is_grounded": True,
        "confidence": retrieval_result.get("confidence", 0.9)
    }

# ── Primary Exam Answer Generator ─────────────────────────────────────────────

def generate_exam_answer(question: str, retrieval_result: Dict[str, Any], 
                         mode: str = "detailed", marks: int = 5) -> Dict[str, Any]:
    """
    Produces a rigorously grounded exam answer.
    Enforces honest insufficiency responses when evidence is lacking.
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
            "confidence": 0.0
        }

    client = get_groq_client()
    if client is None:
        # Graceful, high-fidelity local grounded synthesis
        return _synthesize_grounded_exam_answer_local(question, retrieval_result, mode, marks)

    # Use Groq API with precision-first system prompt
    context = retrieval_result.get("combined_context", "")
    citations = retrieval_result.get("citations", [])

    system_prompt = f"""You are Exam Mate AI, an academic exam preparation specialist.
Answer the user's exam question STRICTLY using the provided source context.
DO NOT fabricate facts, cite unseen pages, or extrapolate beyond the provided text.
If the source does not contain enough evidence, state: 'The supplied material does not contain enough information to answer this question reliably.'

Exam requirements:
- Marks allocated: {marks} marks
- Target style: {mode} (concise for short marks, structured & comprehensive for 5+ marks)
- Always include page references matching the source tags (e.g. [Page X, Section Y]).

Output format: Return valid JSON with this exact structure:
{{
    "definition": "Clear 1-2 sentence core definition",
    "explanation": "Thorough academic explanation",
    "points": ["Numbered key point 1 [Page X]", "Numbered key point 2 [Page Y]"],
    "examples": ["Example directly present in text [Page Z]"],
    "conclusion": "Final summarizing sentence"
}}
"""

    user_prompt = f"""Context from uploaded study material:
{context}

Question:
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
                max_tokens=1200,
                response_format={"type": "json_object"}
            )
            raw_content = resp.choices[0].message.content
            parsed = json.loads(raw_content)

            # Build readable answer string
            text_lines = [
                f"### 1. Definition\n{parsed.get('definition', '')}",
                f"\n### 2. Explanation\n{parsed.get('explanation', '')}",
                f"\n### 3. Key Points\n" + "\n".join([f"{i+1}. {pt}" for i, pt in enumerate(parsed.get('points', []))])
            ]
            if parsed.get('examples'):
                text_lines.append(f"\n### 4. Examples\n" + "\n".join([f"- {ex}" for ex in parsed.get('examples', [])]))
            text_lines.append(f"\n### 5. Conclusion\n{parsed.get('conclusion', '')}")

            return {
                "answer_text": "\n".join(text_lines),
                "structured_answer": parsed,
                "citations": citations,
                "is_grounded": True,
                "confidence": retrieval_result.get("confidence", 0.95)
            }
        except Exception as e:
            continue

    # Fallback if API call failed
    return _synthesize_grounded_exam_answer_local(question, retrieval_result, mode, marks)

# ── Flashcard Generator ───────────────────────────────────────────────────────

def generate_flashcards_from_chunks(chunks: List[Dict[str, Any]], count: int = 5) -> List[Dict[str, Any]]:
    """Generates revision flashcards grounded in source passages with page attribution."""
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
                        front = f"What is {subject}?"
                        back = f"{subject} {s_clean[match.start():].strip()}"
                        cards.append({
                            "front": front,
                            "back": back,
                            "source_page": p_no,
                            "source_snippet": s_clean[:180]
                        })
                        if len(cards) >= count:
                            return cards

    # Fallback to key sentences
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
    Each item has 4 options, the 0-indexed correct answer, explanation, and cited source page.
    """
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
                # Create question from this statement
                q_text = f"According to Page {p_no}, which of the following is correct regarding: {s_clean[:40]}...?"
                correct_opt = s_clean
                if len(correct_opt) > 120:
                    correct_opt = correct_opt[:117] + "..."

                options = [
                    correct_opt,
                    distractor_pool[(len(questions) * 2) % len(distractor_pool)],
                    distractor_pool[(len(questions) * 2 + 1) % len(distractor_pool)],
                    distractor_pool[(len(questions) * 2 + 2) % len(distractor_pool)]
                ]
                # Rotate correct option index so it's not always 0
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

    # If needed, fill remaining questions from chunk summaries
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
