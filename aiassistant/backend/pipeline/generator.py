import json
import re
import os
import traceback
import time
from urllib.parse import quote_plus
from groq import Groq

# Configuration
GROQ_API_KEY = os.environ.get("GROQ_API_KEY")
GROQ_MODEL = os.environ.get("GROQ_MODEL", "llama-3.3-70b-versatile")
client = Groq(api_key=GROQ_API_KEY) if GROQ_API_KEY else None

# ── Diagram type selection helpers ────────────────────────────────────────────

_DIAGRAM_RULES = [
    # (keywords_in_query, diagram_type, description)
    (["flow", "process", "pipeline", "workflow", "steps", "procedure"],
     "flowchart", "A left-to-right flowchart of the main process"),
    (["sequence", "protocol", "communication", "message", "request", "response", "handshake"],
     "sequenceDiagram", "A sequence diagram showing message exchanges"),
    (["class", "object", "oop", "inheritance", "polymorphism", "uml", "design pattern"],
     "classDiagram", "A UML class diagram"),
    (["state", "machine", "transition", "automaton", "finite"],
     "stateDiagram-v2", "A state machine diagram"),
    (["er ", "entity", "relation", "database", "table", "schema", "sql"],
     "erDiagram", "An entity-relationship diagram"),
    (["timeline", "history", "evolution", "era", "period", "age", "century"],
     "timeline", "A timeline diagram"),
    (["gantt", "schedule", "project", "task", "milestone", "deadline"],
     "gantt", "A Gantt chart"),
    (["mind", "concept", "map", "brainstorm", "topic", "subtopic"],
     "mindmap", "A mind-map diagram"),
    (["pie", "proportion", "percentage", "distribution", "share", "ratio"],
     "pie", "A pie chart"),
    (["graph", "network", "topology", "architecture", "layer", "component", "system", "cycle"],
     "graph", "A graph / architecture diagram"),
]

_MERMAID_TEMPLATES = {
    "flowchart": "flowchart LR\n    A[Start] --> B{Decision}\n    B -- Yes --> C[Process A]\n    B -- No --> D[Process B]\n    C --> E[End]\n    D --> E",
    "sequenceDiagram": "sequenceDiagram\n    participant A\n    participant B\n    A->>B: Request\n    B-->>A: Response",
    "classDiagram": "classDiagram\n    class Animal {\n        +String name\n        +move()\n    }\n    class Dog {\n        +bark()\n    }\n    Animal <|-- Dog",
    "stateDiagram-v2": "stateDiagram-v2\n    [*] --> Idle\n    Idle --> Running : start\n    Running --> Idle : stop\n    Running --> [*] : done",
    "erDiagram": "erDiagram\n    CUSTOMER ||--o{ ORDER : places\n    ORDER ||--|{ LINE-ITEM : contains",
    "timeline": "timeline\n    title History of Events\n    section Era 1\n        1990 : Event A\n        1995 : Event B\n    section Era 2\n        2000 : Event C",
    "gantt": "gantt\n    title Project Schedule\n    dateFormat  YYYY-MM-DD\n    section Phase 1\n    Task A :a1, 2024-01-01, 7d\n    Task B :after a1, 5d",
    "mindmap": "mindmap\n  root((Main Topic))\n    Branch A\n      Sub A1\n      Sub A2\n    Branch B\n      Sub B1",
    "pie": "pie title Distribution\n    \"Category A\" : 40\n    \"Category B\" : 35\n    \"Category C\" : 25",
    "graph": "graph TD\n    A[Input] --> B[Processing]\n    B --> C[Output]\n    B --> D[Storage]",
}


def _pick_diagram_type(query: str) -> tuple[str, str]:
    """Return (diagram_type, description) based on the query keywords."""
    q = query.lower()
    for keywords, dtype, desc in _DIAGRAM_RULES:
        if any(kw in q for kw in keywords):
            return dtype, desc
    return "graph", "A structural diagram for the topic"


# Simple circuit breaker state
_groq_cooldown_until = 0

def _groq_completion_with_fallback(messages, response_format=None, temperature=0.2, max_tokens=1500):
    """
    Handles Groq API calls with a lightweight circuit breaker.
    If the primary model is rate-limited, it switches to a fallback model 
    and enters a cooldown period to avoid sequential retries and latency spikes.
    """
    global _groq_cooldown_until
    if client is None:
        raise RuntimeError("GROQ_API_KEY not configured")

    # If in cooldown, start with the fallback model
    current_time = time.time()
    if current_time < _groq_cooldown_until:
        models_to_try = ["llama-3.1-8b-instant", GROQ_MODEL]
    else:
        models_to_try = [GROQ_MODEL, "llama-3.1-8b-instant"]
    
    for model_name in models_to_try:
        try:
            params = {
                "model": model_name,
                "messages": messages,
                "temperature": temperature,
                "max_tokens": max_tokens
            }
            if response_format:
                params["response_format"] = response_format
            
            return client.chat.completions.create(**params)
        except Exception as e:
            err_msg = str(e).lower()
            if "429" in err_msg or "rate limit" in err_msg or "503" in err_msg:
                # If the primary model fails, trigger/extend cooldown
                if model_name == GROQ_MODEL:
                    print(f"[Groq] Primary model {model_name} rate limited. Entering 30s cooldown.")
                    _groq_cooldown_until = time.time() + 30
                continue
            else:
                print(f"[Groq Error] {model_name}: {e}")
                break
                    
    raise RuntimeError("All Groq models failed or were rate limited.")


def fix_mermaid_diagram(broken_code: str, error_message: str, diagram_type: str) -> str:
    """
    Uses Groq to self-correct a broken Mermaid diagram.
    Returns corrected Mermaid code as a plain string.
    """
    if client is None:
        return _MERMAID_TEMPLATES.get(diagram_type, _MERMAID_TEMPLATES["graph"])

    fix_prompt = f"""You are a Mermaid.js syntax expert. Fix the following broken Mermaid diagram.

DIAGRAM TYPE: {diagram_type}
ERROR: {error_message}

BROKEN CODE:
```
{broken_code}
```

STRICT RULES:
1. Output ONLY the corrected Mermaid code — no markdown fences, no explanation, no extra text.
2. The first line MUST start with the diagram type keyword (e.g. 'graph TD', 'flowchart LR', 'sequenceDiagram', etc.).
3. Fix ALL syntax errors — missing arrows, wrong keywords, unclosed brackets, illegal characters.
4. Node labels with spaces MUST use quotes: A["Label with spaces"].
5. Use only basic ASCII in node IDs (no spaces, no special chars).
6. Keep the diagrams semantically meaningful.
7. Output must be valid Mermaid that renders without any errors.
"""

    try:
        completion = _groq_completion_with_fallback(
            messages=[
                {"role": "system", "content": "You are a Mermaid.js syntax fixer. Output only corrected Mermaid code, never wrap in markdown."},
                {"role": "user", "content": fix_prompt},
            ],
            temperature=0.1,
            max_tokens=1024,
        )
        fixed = completion.choices[0].message.content.strip()
        # Strip markdown fences if the model wraps them anyway
        fixed = re.sub(r"^```[a-z]*\n?", "", fixed, flags=re.IGNORECASE).strip()
        fixed = re.sub(r"\n?```$", "", fixed).strip()
        return fixed
    except Exception as exc:
        print(f"[Mermaid Fix] Groq error: {exc}")
        return _MERMAID_TEMPLATES.get(diagram_type, _MERMAID_TEMPLATES["graph"])


def generate_diagrams(query: str, context: str) -> list[dict]:
    """
    Generates one or more AI-powered Mermaid diagrams for the given query.
    Each diagram dict contains: type, diagram_type, code, title, description.
    """
    if client is None:
        diagram_type, desc = _pick_diagram_type(query)
        return [{
            "type": "mermaid",
            "diagram_type": diagram_type,
            "title": f"Diagram: {query[:60]}",
            "description": desc,
            "code": _MERMAID_TEMPLATES.get(diagram_type, _MERMAID_TEMPLATES["graph"]),
        }]

    diagram_type, description = _pick_diagram_type(query)
    template_example = _MERMAID_TEMPLATES.get(diagram_type, _MERMAID_TEMPLATES["graph"])

    prompt = f"""You are a Mermaid.js diagram expert for academic education.

TOPIC: {query}
CONTEXT (optional): {context[:1500]}
REQUIRED DIAGRAM TYPE: {diagram_type}

Generate a detailed, educational Mermaid.js diagram for the topic above.

STRICT RULES:
1. Output ONLY the Mermaid code — no markdown fences (no ```), no explanation.
2. First line MUST be the diagram keyword: '{diagram_type}' (or 'graph TD' / 'flowchart LR' etc.).
3. Node labels containing spaces or special characters MUST use double-quotes: A["Label text"].
4. Node IDs must be plain alphanumeric with underscores only: node_A, step1, etc.
5. Include at least 6-10 meaningful nodes/steps relevant to the topic.
6. Must render without syntax errors in Mermaid.js v10+.

EXAMPLE STRUCTURE for {diagram_type}:
{template_example}

Now generate the diagram for: {query}
"""

    try:
        completion = _groq_completion_with_fallback(
            messages=[
                {"role": "system", "content": "You are a Mermaid.js diagram generator. Output only valid Mermaid code. Never use markdown code fences."},
                {"role": "user", "content": prompt},
            ],
            temperature=0.2,
            max_tokens=1500,
        )
        code = completion.choices[0].message.content.strip()
        # Strip accidental markdown fences
        code = re.sub(r"^```[a-z]*\n?", "", code, flags=re.IGNORECASE).strip()
        code = re.sub(r"\n?```$", "", code).strip()

        if not code:
            raise ValueError("Empty response from Groq")

        return [{
            "type": "mermaid",
            "diagram_type": diagram_type,
            "title": f"{query[:60]}",
            "description": description,
            "code": code,
        }]

    except Exception as exc:
        print(f"[Mermaid Gen] Error generating diagram: {exc}")
        return [{
            "type": "mermaid",
            "diagram_type": diagram_type,
            "title": f"Diagram: {query[:60]}",
            "description": description,
            "code": _MERMAID_TEMPLATES.get(diagram_type, _MERMAID_TEMPLATES["graph"]),
        }]


def generate_exam_answer(query, context, mode="detailed", marks=5):
    """
    Unified Pure-Groq Pipeline for University-Grade Academic Answers.
    Uses Llama 3.3 70B for massive, structured responses.
    """

    # Dynamic instruction based on marks
    marks_int = int(marks)
    if marks_int <= 2:
        detail_instruction = "WORD LIMIT: 30-50 words. STRUCTURE: Definition + One Key Point/Example."
    elif marks_int <= 5:
        detail_instruction = "WORD LIMIT: 100-150 words. STRUCTURE: Introduction + Main Points (bullets) + Conclusion."
    elif marks_int <= 10:
        detail_instruction = "WORD LIMIT: 250-350 words. STRUCTURE: Introduction + Definition + Deep Explanation + Feature Points (5-6) + Example + Conclusion."
    else:  # 16 marks
        detail_instruction = "EXHAUSTIVE WORD LIMIT: 800-1200 words. STRUCTURE: Professional Introduction + Historical Background + Detailed Technical Explanation + Technical Diagram Description + Step-by-Step Working Process + Advantages (5-6) + Disadvantages (3-4) + Real-world Applications + Powerful Conclusion."

    prompt = f"""
    You are an AI University Professor. Provide a highly structured exam answer for: '{query}'.
    MARKS: {marks}
    REQUIREMENT: {detail_instruction}

    CONTEXT:
    {context[:3000]}

    You MUST respond with a valid JSON matching this schema. Use university-level English.
    {{
      "title": "Topic Title",
      "introduction": "Intro paragraph",
      "definition": "Formal definition",
      "explanation": "Detailed theoretical explanation (This must be very long for 16-marks)",
      "working_process": "Step-by-step how it works",
      "points": ["Key Point 1", "Key Point 2", ...],
      "example": "Real-world example",
      "advantages": ["Advantage 1", "Advantage 2"],
      "disadvantages": ["Disadvantage 1", "Disadvantage 2"],
      "applications": ["Application 1", "Application 2"],
      "conclusion": "Final academic summary",
      "image_prompt": "A professional whiteboard-style technical diagram or flow-chart description for {query}. Educational clarity, high-contrast, clear labels."
    }}

    STRICT COMPLIANCE: For high-mark questions (10 and 16 marks), generate massive content for the 'explanation' and 'working_process' fields.
    """

    try:
        completion = _groq_completion_with_fallback(
            messages=[
                {"role": "system", "content": "You are a JSON-only Academic API. Never use markdown code blocks. Output pure JSON only."},
                {"role": "user", "content": prompt}
            ],
            response_format={"type": "json_object"},
            temperature=0.3,
            max_tokens=4096
        )

        response_text = completion.choices[0].message.content.strip()

        # Security Cleaning
        start_idx = response_text.find('{')
        end_idx = response_text.rfind('}')
        if start_idx != -1 and end_idx != -1:
            response_text = response_text[start_idx:end_idx+1]

        structured_response = json.loads(response_text, strict=False)

        # Logic for Visuals (Zero-Config Pollinations Rendering)
        raw_iprompt = structured_response.get("image_prompt", query)

        visual_style = "professional architectural diagram, whiteboard style, high resolution, sharp text labels, white background, educational schematic"
        final_iprompt = f"{raw_iprompt}, {visual_style}"

        structured_response["image_url"] = f"https://pollinations.ai/p/{quote_plus(final_iprompt)}?width=1024&height=1024&seed=42&model=flux"
        structured_response["image_prompt"] = raw_iprompt

    except Exception as e:
        print(f"Groq Pure Pipeline Error: {e}")
        traceback.print_exc()

        structured_response = {
            "title": "Assistant Offline",
            "introduction": "An error occurred during content generation.",
            "definition": "The system encountered a configuration issue.",
            "explanation": f"Detailed Error: {str(e)}. Please check your Groq API key.",
            "points": ["Verify Internet Connection.", "Check API token status."],
            "conclusion": "Please retry in a moment."
        }

    diagrams = generate_diagrams(query, context)
    return structured_response, diagrams


def detect_keywords(text):
    """
    Extracts key academic terms from the text for tagging.
    """
    try:
        words = re.findall(r'\b[A-Za-z]{6,}\b', text)
        return list(set(words))[:5]
    except Exception:
        return []
