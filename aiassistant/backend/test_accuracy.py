import os
import sys
import json
import time
import tempfile
import fitz
from pptx import Presentation
from pptx.util import Inches

# Append backend directory to path
sys.path.append(os.path.dirname(__file__))

from app import app
from db import DatabaseManager
from pipeline.extractor import (
    clean_text,
    calculate_confidence_score,
    strip_repeated_headers_footers,
    extract_pdf_precision,
    extract_pptx_precision,
    process_document
)
from pipeline.retriever import PrecisionRetriever
from pipeline.generator import (
    generate_exam_answer,
    generate_flashcards_from_chunks,
    generate_quiz_from_chunks
)

def run_precision_evaluation_suite():
    print("=" * 70)
    print("  EXAM MATE AI — ACCURACY & EXTRACTION EVALUATION SUITE")
    print("=" * 70)

    results = {
        "passed": 0,
        "failed": 0,
        "tests": []
    }

    def record_test(name: str, passed: bool, detail: str = ""):
        if passed:
            results["passed"] += 1
            print(f"  [PASS] {name} {f'({detail})' if detail else ''}")
        else:
            results["failed"] += 1
            print(f"  [FAIL] {name} - {detail}")
        results["tests"].append({"name": name, "passed": passed, "detail": detail})

    # ── Test 1: Text Cleaning and Hyphenation Recovery ────────────────────────
    raw_hyphenated = "This is a sophisti-\n cated multi-layer neural network architec-\n ture with high through-\n put."
    cleaned = clean_text(raw_hyphenated)
    expected_words = ["sophisticated", "architecture", "throughput"]
    hyphen_ok = all(w in cleaned for w in expected_words)
    record_test("Text Cleaning: Hyphenation Across Linebreaks", hyphen_ok, "Recombined words accurately")

    # ── Test 2: Repeated Header/Footer Stripping ──────────────────────────────
    dummy_pages = [
        "ADVANCED OPERATING SYSTEMS\nPage content 1\nPage 1",
        "ADVANCED OPERATING SYSTEMS\nPage content 2\nPage 2",
        "ADVANCED OPERATING SYSTEMS\nPage content 3\nPage 3",
        "ADVANCED OPERATING SYSTEMS\nPage content 4\nPage 4"
    ]
    cleaned_pages, removed = strip_repeated_headers_footers(dummy_pages)
    header_ok = "ADVANCED OPERATING SYSTEMS" in removed
    record_test("Header/Footer Detection: Running Headers Stripped", header_ok, f"Removed {len(removed)} repeating patterns")

    # ── Test 3: Synthetic Academic Digital PDF with Tables & Headings ─────────
    with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp_pdf:
        pdf_path = tmp_pdf.name

    doc = fitz.open()
    # Page 1: Title and Operating System Concepts
    p1 = doc.new_page(width=612, height=792)
    p1.insert_textbox(fitz.Rect(50, 50, 550, 400),
                      "OPERATING SYSTEMS ARCHITECTURE\n\n"
                      "A microkernel is an operating system architecture that minimizes the amount of code running in kernel space. "
                      "It provides basic mechanisms such as address space management, thread management, and inter-process communication (IPC). "
                      "For example, the QNX and L4 microkernels operate on this design principle.\n\n"
                      "VIRTUAL MEMORY MANAGEMENT\n\n"
                      "Paging is a memory management scheme that eliminates the need for contiguous allocation of physical memory. "
                      "The page table translates virtual page numbers to physical frame numbers. "
                      "When a process accesses a page not present in main memory, a page fault exception is triggered.",
                      fontsize=11)

    # Page 2: Table and Multi-column
    p2 = doc.new_page(width=612, height=792)
    p2.insert_textbox(fitz.Rect(50, 50, 550, 400),
                      "PROCESS SCHEDULING ALGORITHMS\n\n"
                      "First-Come First-Served (FCFS) schedules processes in arrival order and suffers from the convoy effect.\n\n"
                      "Shortest Job First (SJF) provides optimal average waiting time for a given set of processes.\n\n"
                      "Round Robin (RR) allocates a fixed time quantum to each ready process.",
                      fontsize=11)
    doc.save(pdf_path)
    doc.close()

    ext_pdf = extract_pdf_precision(pdf_path)
    os.remove(pdf_path)

    pdf_text_ok = "microkernel" in ext_pdf["raw_text"].lower() and "page fault" in ext_pdf["raw_text"].lower()
    record_test("PDF Precision Extraction: Digital Text & Headings", pdf_text_ok, f"Score: {ext_pdf['confidence_score']}%")

    # ── Test 4: PowerPoint PPTX Extraction with Hierarchy & Notes ─────────────
    with tempfile.NamedTemporaryFile(suffix=".pptx", delete=False) as tmp_pptx:
        pptx_path = tmp_pptx.name

    prs = Presentation()
    slide_layout = prs.slide_layouts[1] # title and content
    slide = prs.slides.add_slide(slide_layout)
    slide.shapes.title.text = "Distributed Systems Fundamentals"
    tf = slide.shapes.placeholders[1].text_frame
    tf.text = "Core Challenges in Distributed Systems"
    p_sub = tf.add_paragraph()
    p_sub.text = "Network partitions and CAP theorem"
    p_sub.level = 1
    # Add speaker notes
    notes_slide = slide.notes_slide
    notes_tf = notes_slide.notes_text_frame
    notes_tf.text = "Emphasize Brewer's conjecture during examination review."

    prs.save(pptx_path)

    ext_pptx = extract_pptx_precision(pptx_path)
    os.remove(pptx_path)

    pptx_ok = "Distributed Systems Fundamentals" in ext_pptx["raw_text"] and "Brewer's conjecture" in ext_pptx["raw_text"]
    record_test("PPTX Precision Extraction: Hierarchy & Speaker Notes", pptx_ok, f"Confidence: {ext_pptx['confidence_score']}%")

    # ── Test 5: End-to-End Database & Flask API Authentication ────────────────
    client = app.test_client()
    test_user_email = f"eval_student_{int(time.time())}@exam.ai"
    reg_resp = client.post("/api/auth/register", json={
        "name": "Alex Mercer",
        "email": test_user_email,
        "password": "Password123!"
    })
    auth_ok = reg_resp.status_code == 201
    token = reg_resp.get_json().get("token")
    user_id = reg_resp.get_json().get("user", {}).get("id")
    record_test("Authentication: Registration & JWT Token Issuance", auth_ok and bool(token), f"User ID: {user_id[:8]}...")

    headers = {"Authorization": f"Bearer {token}"}

    # ── Test 6: Document Upload & Structured Chunking ─────────────────────────
    with tempfile.NamedTemporaryFile(suffix=".txt", delete=False, mode="w", encoding="utf-8") as tmp_txt:
        tmp_txt.write("COMPILER DESIGN\n\n"
                      "Lexical analysis is the first phase of a compiler. It converts a sequence of characters into a sequence of tokens.\n\n"
                      "Syntax analysis verifies that the token sequence satisfies the grammatical rules of the programming language using Context-Free Grammars.\n\n"
                      "Semantic analysis checks for type compatibility, undeclared identifiers, and scope resolution.\n\n"
                      "Code generation converts the intermediate representation into target machine code.")
        txt_path = tmp_txt.name

    with open(txt_path, "rb") as f:
        up_resp = client.post("/api/upload", data={"file": f}, headers=headers)
    os.remove(txt_path)

    upload_ok = up_resp.status_code == 201
    doc_id = up_resp.get_json().get("document", {}).get("id") if upload_ok else None
    record_test("API Document Upload: Chunks & Metadata Persistence", upload_ok and bool(doc_id), f"Document ID: {doc_id}")

    # ── Test 7: Grounded Retrieval with Page Citations ────────────────────────
    ask_resp = client.post("/api/ask", json={
        "question": "What is the primary function of lexical analysis in compiler design?",
        "document_id": doc_id,
        "marks": 5,
        "mode": "detailed"
    }, headers=headers)

    ask_data = ask_resp.get_json()
    grounded_ok = ask_resp.status_code == 200 and ask_data.get("is_grounded") is True and len(ask_data.get("citations", [])) > 0
    citation_page = ask_data.get("citations", [{}])[0].get("page", "N/A")
    record_test("Precision RAG: Source-Grounded Answer with Page Citations", grounded_ok, f"Cited Page: {citation_page}")

    # ── Test 8: Insufficient Evidence Fallback Check ──────────────────────────
    irrelevant_resp = client.post("/api/ask", json={
        "question": "Explain the geological formation of volcanic islands in the Pacific Ocean.",
        "document_id": doc_id,
        "marks": 5
    }, headers=headers)

    irr_data = irrelevant_resp.get_json()
    honest_ok = irr_data.get("is_grounded") is False and "not contain enough information" in irr_data.get("answer_text", "")
    record_test("Honest Fallback: Rejection of Unsupported Questions", honest_ok, "Triggered honest insufficiency response")

    # ── Test 9: Flashcards & Spaced Repetition (SM-2) Scheduling ─────────────
    fc_resp = client.post("/api/flashcards/generate", json={
        "document_id": doc_id,
        "deck_title": "Compiler Design Deck",
        "count": 3
    }, headers=headers)

    fc_data = fc_resp.get_json()
    fc_gen_ok = fc_resp.status_code == 201 and len(fc_data.get("cards", [])) > 0
    first_card = fc_data.get("cards", [{}])[0]
    card_id = first_card.get("id")
    record_test("Flashcards: Automatic Concept Extraction from Chunks", fc_gen_ok, f"Generated {len(fc_data.get('cards', []))} cards")

    # Review with 'Good' rating
    rev_resp = client.post("/api/flashcards/review", json={
        "card_id": card_id,
        "rating": "Good"
    }, headers=headers)
    rev_data = rev_resp.get_json()
    sm2_ok = rev_data.get("interval_days", 0) >= 1
    record_test("Spaced Repetition (SM-2): Review Interval Recalculation", sm2_ok, f"Next interval: {rev_data.get('interval_days')} day(s)")

    # ── Test 10: Quiz Generation & Server-Side Scoring ────────────────────────
    quiz_resp = client.post("/api/quizzes/generate", json={
        "document_id": doc_id,
        "title": "Compiler Design Mastery Quiz",
        "count": 3
    }, headers=headers)

    quiz_data = quiz_resp.get_json().get("quiz", {})
    quiz_id = quiz_data.get("id")
    q_items = quiz_data.get("questions", [])
    quiz_gen_ok = bool(quiz_id) and len(q_items) > 0
    record_test("Quiz System: Multiple Choice Generation with Distractors", quiz_gen_ok, f"{len(q_items)} questions generated")

    # Submit quiz answers
    answers = [q.get("correct_option_index", 0) for q in q_items]
    sub_resp = client.post(f"/api/quizzes/{quiz_id}/submit", json={"answers": answers}, headers=headers)
    sub_data = sub_resp.get_json()
    scoring_ok = sub_resp.status_code == 200 and sub_data.get("percentage") == 100.0
    record_test("Quiz System: Server-Side Scoring & Breakdown", scoring_ok, f"Score: {sub_data.get('score')}/{sub_data.get('total')} (100%)")

    # ── Test 11: Planner, Exams & Study Tasks ─────────────────────────────────
    future_exam_date = "2026-12-15T09:00:00"
    exam_resp = client.post("/api/exams", json={
        "title": "Final Compiler Engineering",
        "subject": "Computer Science",
        "exam_date": future_exam_date,
        "target_score": 95,
        "syllabus": "Modules 1-5: Lexical, Syntax, Semantic, Code Gen"
    }, headers=headers)
    exam_id = exam_resp.get_json().get("id")

    task_resp = client.post("/api/tasks", json={
        "title": "Review Lexical Analysis State Diagrams",
        "exam_id": exam_id,
        "priority": "high",
        "due_date": "2026-11-01T18:00:00"
    }, headers=headers)
    task_id = task_resp.get_json().get("id")

    toggle_resp = client.post(f"/api/tasks/{task_id}/toggle", headers=headers)
    planner_ok = exam_resp.status_code == 201 and task_resp.status_code == 201 and toggle_resp.status_code == 200
    record_test("Study Planner: Exam Scheduling & Task Management", planner_ok, "Exam + Task + Toggle verified")

    # ── Test 12: Focus Session & Real Analytics Summary ───────────────────────
    focus_resp = client.post("/api/focus", json={
        "duration_minutes": 45,
        "subject": "Compilers & Parsers",
        "notes": "Reviewed LR parser state transitions"
    }, headers=headers)

    analytics_resp = client.get("/api/analytics", headers=headers)
    an_data = analytics_resp.get_json()
    analytics_ok = an_data.get("total_focus_minutes", 0) >= 45 and an_data.get("total_documents", 0) >= 1
    record_test("Focus & Analytics: Real Session Logging & Metrics", analytics_ok, f"Focus: {an_data.get('total_focus_minutes')} min, Docs: {an_data.get('total_documents')}")

    # ── Test 13: System Health Check ──────────────────────────────────────────
    health_resp = client.get("/api/health")
    health_ok = health_resp.status_code == 200 and health_resp.get_json().get("status") == "healthy"
    record_test("System Health: API Diagnostic & Endpoint Readiness", health_ok, "Status: Healthy")

    print("=" * 70)
    print(f"  TOTAL TESTS: {len(results['tests'])} | PASSED: {results['passed']} | FAILED: {results['failed']}")
    print("=" * 70)

    return results

if __name__ == "__main__":
    res = run_precision_evaluation_suite()
    if res["failed"] > 0:
        sys.exit(1)
    else:
        sys.exit(0)
