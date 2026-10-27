import os
import re
import time
import tempfile
import fitz  # PyMuPDF
import pdfplumber
from typing import List, Dict, Any, Tuple

# ── Text Cleaning Utilities ───────────────────────────────────────────────────

COMMON_DICTIONARY_WORDS = {
    "the", "be", "to", "of", "and", "a", "in", "that", "have", "i", "it", "for", "not",
    "on", "with", "he", "as", "you", "do", "at", "this", "but", "his", "by", "from",
    "they", "we", "say", "her", "she", "or", "an", "will", "my", "one", "all", "would",
    "there", "their", "what", "so", "up", "out", "if", "about", "who", "get", "which",
    "go", "me", "when", "make", "can", "like", "time", "no", "just", "him", "know",
    "take", "people", "into", "year", "your", "good", "some", "could", "them", "see",
    "other", "than", "then", "now", "look", "only", "come", "its", "over", "think",
    "also", "back", "after", "use", "two", "how", "our", "work", "first", "well",
    "way", "even", "new", "want", "because", "any", "these", "give", "day", "most", "us",
    "system", "function", "data", "model", "algorithm", "process", "result", "analysis",
    "design", "method", "example", "structure", "value", "table", "definition", "computer",
    "network", "memory", "input", "output", "learning", "database", "exam", "answer", "study"
}

def clean_text(text: str) -> str:
    """
    Precision text cleaning:
    - Recombines hyphenated words split across line breaks (e.g. 'imple- \n mentation' -> 'implementation')
    - Cleans non-breaking spaces and anomalous whitespace
    - Normalizes multiple blank lines to at most two
    - Preserves math expressions, symbols, punctuation, code blocks, and numbers
    """
    if not text:
        return ""

    # Recombine hyphenated line breaks
    text = re.sub(r'(\b[a-zA-Z]{2,})-\s*\n\s*([a-zA-Z]{2,}\b)', r'\1\2', text)

    # Replace weird space characters with normal space
    text = text.replace('\xa0', ' ').replace('\u200b', '').replace('\r\n', '\n').replace('\r', '\n')

    # Remove repeated trailing spaces on lines
    lines = [re.sub(r'[ \t]+$', '', line) for line in text.split('\n')]
    
    # Filter repeated empty lines
    cleaned_lines = []
    empty_count = 0
    for line in lines:
        if not line.strip():
            empty_count += 1
            if empty_count <= 2:
                cleaned_lines.append("")
        else:
            empty_count = 0
            cleaned_lines.append(line)

    return "\n".join(cleaned_lines).strip()

def strip_repeated_headers_footers(page_texts: List[str]) -> Tuple[List[str], List[str]]:
    """
    Identifies and strips running headers/footers repeated across 3 or more consecutive pages.
    """
    if len(page_texts) < 3:
        return page_texts, []

    first_lines = {}
    last_lines = {}

    for idx, p in enumerate(page_texts):
        lines = [line.strip() for line in p.split('\n') if line.strip()]
        if lines:
            first_lines[idx] = lines[0]
            last_lines[idx] = lines[-1]

    # Find common repeated header/footer lines
    header_counts = {}
    for h in first_lines.values():
        if len(h) > 4:
            header_counts[h] = header_counts.get(h, 0) + 1

    footer_counts = {}
    for f in last_lines.values():
        if len(f) > 3:
            footer_counts[f] = footer_counts.get(f, 0) + 1

    common_headers = {h for h, c in header_counts.items() if c >= 3}
    common_footers = {f for f, c in footer_counts.items() if c >= 3}

    cleaned_pages = []
    removed_patterns = list(common_headers.union(common_footers))

    for idx, p in enumerate(page_texts):
        lines = p.split('\n')
        filtered = []
        for line in lines:
            s_line = line.strip()
            if s_line in common_headers or s_line in common_footers:
                continue
            # Also strip isolated page numbers like 'Page 12' or '- 12 -'
            if re.match(r'^(page\s+\d+|\d+|\-\s*\d+\s*\-)$', s_line, re.IGNORECASE):
                continue
            filtered.append(line)
        cleaned_pages.append("\n".join(filtered))

    return cleaned_pages, removed_patterns

# ── Confidence Score Calculation ───────────────────────────────────────────────

def calculate_confidence_score(text: str, total_pages: int, ocr_used: bool, warnings: List[str]) -> float:
    """
    Calculates a transparent, mathematically grounded extraction confidence score (0-100%):
    - Dictionary validity: ratio of tokens that match recognized words/identifiers (weight: 50%)
    - Text density: average characters per page vs expected threshold (weight: 35%)
    - Structural integrity: absence of severe warnings or unhandled scanned pages (weight: 15%)
    """
    if not text.strip():
        return 0.0

    tokens = re.findall(r'\b[a-zA-Z]{3,}\b', text.lower())
    if not tokens:
        return 15.0

    valid_words = sum(1 for t in tokens if t in COMMON_DICTIONARY_WORDS)
    dict_ratio = valid_words / len(tokens)
    # Scale dictionary score: even technical docs typically hit 30-50% common words
    dict_score = min(1.0, dict_ratio / 0.40) * 50.0

    # Text density score (expect at least 250 chars per page on average)
    avg_chars = len(text) / max(1, total_pages)
    density_score = min(1.0, avg_chars / 250.0) * 35.0

    # Structure & warning penalties
    penalty = 0.0
    for w in warnings:
        if "low text density" in w.lower():
            penalty += 5.0
        elif "failed" in w.lower():
            penalty += 10.0
    if ocr_used:
        penalty += 3.0  # OCR inherently has slight character error variance

    structure_score = max(0.0, 15.0 - penalty)
    confidence = round(min(100.0, max(5.0, dict_score + density_score + structure_score)), 1)
    return confidence

# ── Stage B: Format-Specific Extractors ───────────────────────────────────────

def extract_pdf_precision(pdf_path: str) -> Dict[str, Any]:
    """
    Extracts PDF documents preserving:
    - Multi-column reading order
    - Section headings based on font size & layout
    - Tables converted to structured Markdown
    - Page attribution
    - Scanned page detection with OCR fallback
    """
    warnings = []
    text_blocks = []
    raw_pages = []
    ocr_used = False
    start_time = time.time()

    doc = fitz.open(pdf_path)
    page_count = len(doc)
    processed_pages = 0

    # Step 1: Extract tables per page using pdfplumber
    tables_per_page = {}
    try:
        with pdfplumber.open(pdf_path) as plum:
            for p_idx, p in enumerate(plum.pages):
                extracted_tables = p.extract_tables()
                if extracted_tables:
                    markdown_tables = []
                    for t in extracted_tables:
                        if not t or len(t) < 1:
                            continue
                        clean_rows = []
                        for row in t:
                            cells = [str(c).replace('\n', ' ').strip() if c else "" for c in row]
                            clean_rows.append(" | ".join(cells))
                        if len(clean_rows) >= 2:
                            # Add markdown header delimiter
                            header_line = "| " + clean_rows[0] + " |"
                            col_count = len(clean_rows[0].split(" | "))
                            delim = "| " + " | ".join(["---"] * col_count) + " |"
                            body_lines = ["| " + r + " |" for r in clean_rows[1:]]
                            md_table = "\n".join([header_line, delim] + body_lines)
                            markdown_tables.append(md_table)
                    if markdown_tables:
                        tables_per_page[p_idx + 1] = markdown_tables
    except Exception as e:
        warnings.append(f"Table detection notice: {str(e)}")

    # Step 2: Extract text using PyMuPDF block layout
    for page_num in range(page_count):
        p_no = page_num + 1
        page = doc.load_page(page_num)
        
        # Check text length
        direct_text = page.get_text("text").strip()
        page_images = page.get_images()

        # Scanned page detection
        if len(direct_text) < 40 and len(page_images) > 0:
            warnings.append(f"Page {p_no}: Low embedded text detected ({len(direct_text)} chars); image scan present.")
            # OCR fallback
            try:
                from paddleocr import PaddleOCR
                ocr_instance = PaddleOCR(use_angle_cls=True, lang='en', show_log=False)
                pix = page.get_pixmap(dpi=150)
                with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tmp_img:
                    pix.save(tmp_img.name)
                    res = ocr_instance.ocr(tmp_img.name, cls=True)
                    os.remove(tmp_img.name)
                
                ocr_text = []
                if res and res[0]:
                    ocr_text = [line[1][0] for line in res[0]]
                if ocr_text:
                    ocr_used = True
                    joined_ocr = clean_text("\n".join(ocr_text))
                    raw_pages.append(joined_ocr)
                    text_blocks.append({
                        "page_number": p_no,
                        "section_title": f"Page {p_no} (Scanned)",
                        "chunk_text": joined_ocr,
                        "chunk_type": "ocr_text"
                    })
                    processed_pages += 1
                    continue
            except Exception as ocr_err:
                warnings.append(f"Page {p_no}: OCR fallback unavailable ({str(ocr_err)}).")

        # Digital text extraction with reading order recovery
        blocks = page.get_text("blocks")
        # PyMuPDF block format: (x0, y0, x1, y1, "text", block_no, block_type)
        # Sort blocks primarily by column if multi-column, then by Y0
        page_width = page.rect.width
        is_two_column = False
        
        # Detect if text spans two distinct horizontal halves
        left_blocks = [b for b in blocks if b[4].strip() and b[2] <= page_width * 0.55]
        right_blocks = [b for b in blocks if b[4].strip() and b[0] >= page_width * 0.45]
        if len(left_blocks) >= 2 and len(right_blocks) >= 2:
            is_two_column = True
            sorted_blocks = sorted(left_blocks, key=lambda b: b[1]) + sorted(right_blocks, key=lambda b: b[1])
        else:
            sorted_blocks = sorted([b for b in blocks if b[4].strip()], key=lambda b: (b[1], b[0]))

        current_heading = f"Page {p_no}"
        page_content_pieces = []

        for b in sorted_blocks:
            b_text = b[4].strip()
            if not b_text:
                continue

            # Check if block looks like a heading: short, uppercase or title case, no terminal period
            first_line = b_text.split('\n')[0].strip()
            if len(first_line) < 70 and not first_line.endswith('.') and (first_line.isupper() or first_line.istitle()):
                current_heading = first_line

            page_content_pieces.append(b_text)

        # Append extracted markdown tables if any exist for this page
        if p_no in tables_per_page:
            for tbl in tables_per_page[p_no]:
                page_content_pieces.append(f"\n[Table on Page {p_no}]\n{tbl}\n")

        full_page_text = clean_text("\n\n".join(page_content_pieces))
        if full_page_text:
            raw_pages.append(full_page_text)
            text_blocks.append({
                "page_number": p_no,
                "section_title": current_heading,
                "chunk_text": full_page_text,
                "chunk_type": "text"
            })
            processed_pages += 1
        else:
            warnings.append(f"Page {p_no}: No readable text found.")

    doc.close()

    # Step 3: Strip repeated running headers & footers
    if len(raw_pages) >= 3:
        cleaned_page_texts, removed_patterns = strip_repeated_headers_footers(raw_pages)
        if removed_patterns:
            warnings.append(f"Filtered {len(removed_patterns)} repeated running header/footer artifacts.")
        for idx, cp in enumerate(cleaned_page_texts):
            if idx < len(text_blocks):
                text_blocks[idx]["chunk_text"] = clean_text(cp)

    duration = round(time.time() - start_time, 2)
    combined_all = "\n\n".join([b["chunk_text"] for b in text_blocks])
    confidence = calculate_confidence_score(combined_all, page_count, ocr_used, warnings)

    return {
        "file_type": "PDF",
        "page_count": page_count,
        "processed_pages": processed_pages,
        "ocr_used": ocr_used,
        "extraction_method": "PyMuPDF + pdfplumber (Hybrid Layout Recovery)",
        "duration_seconds": duration,
        "confidence_score": confidence,
        "warnings": warnings,
        "raw_text": combined_all,
        "blocks": text_blocks
    }

def extract_pptx_precision(pptx_path: str) -> Dict[str, Any]:
    """
    Extracts PowerPoint slides preserving:
    - Slide numbering & titles
    - Bullet hierarchies (levels 0, 1, 2)
    - Tables embedded in slides
    - Speaker notes
    """
    from pptx import Presentation
    warnings = []
    text_blocks = []
    start_time = time.time()

    prs = Presentation(pptx_path)
    total_slides = len(prs.slides)
    processed_slides = 0

    for idx, slide in enumerate(prs.slides):
        slide_no = idx + 1
        slide_title = f"Slide {slide_no}"
        slide_elements = []

        # Find slide title if available
        if slide.shapes.title and slide.shapes.title.text.strip():
            slide_title = slide.shapes.title.text.strip()
            slide_elements.append(f"## {slide_title}")

        for shape in slide.shapes:
            if shape == slide.shapes.title:
                continue

            # Handle text frames and bullets
            if shape.has_text_frame:
                for paragraph in shape.text_frame.paragraphs:
                    p_text = paragraph.text.strip()
                    if not p_text:
                        continue
                    indent = "  " * paragraph.level
                    bullet = "- " if paragraph.level == 0 else "* "
                    slide_elements.append(f"{indent}{bullet}{p_text}")

            # Handle slide tables
            elif shape.has_table:
                table = shape.table
                table_rows = []
                for row in table.rows:
                    cells = [cell.text.replace('\n', ' ').strip() for cell in row.cells]
                    table_rows.append(" | ".join(cells))
                if table_rows:
                    header = "| " + table_rows[0] + " |"
                    col_count = len(table_rows[0].split(" | "))
                    delim = "| " + " | ".join(["---"] * col_count) + " |"
                    body = ["| " + r + " |" for r in table_rows[1:]]
                    slide_elements.append("\n" + "\n".join([header, delim] + body) + "\n")

        # Speaker notes
        if slide.has_notes_slide:
            notes = slide.notes_slide.notes_text_frame.text.strip()
            if notes:
                slide_elements.append(f"\n[Speaker Notes]: {notes}")

        full_slide_text = clean_text("\n".join(slide_elements))
        if full_slide_text:
            text_blocks.append({
                "page_number": slide_no,
                "section_title": slide_title,
                "chunk_text": full_slide_text,
                "chunk_type": "slide"
            })
            processed_slides += 1
        else:
            warnings.append(f"Slide {slide_no}: Contains no text shapes.")

    duration = round(time.time() - start_time, 2)
    combined = "\n\n".join([b["chunk_text"] for b in text_blocks])
    confidence = calculate_confidence_score(combined, total_slides, False, warnings)

    return {
        "file_type": "PPTX",
        "page_count": total_slides,
        "processed_pages": processed_slides,
        "ocr_used": False,
        "extraction_method": "python-pptx (Hierarchy & Notes Recovery)",
        "duration_seconds": duration,
        "confidence_score": confidence,
        "warnings": warnings,
        "raw_text": combined,
        "blocks": text_blocks
    }

def extract_docx_precision(docx_path: str) -> Dict[str, Any]:
    """
    Extracts Word (.docx) files preserving:
    - Headings (H1, H2, H3)
    - Paragraph text and bullet lists
    - Document tables formatted as Markdown
    """
    from docx import Document
    warnings = []
    text_blocks = []
    start_time = time.time()

    doc = Document(docx_path)
    current_heading = "General"
    current_section_lines = []
    section_index = 1

    for para in doc.paragraphs:
        txt = para.text.strip()
        if not txt:
            continue

        if para.style.name.startswith("Heading"):
            if current_section_lines:
                sec_text = clean_text("\n".join(current_section_lines))
                text_blocks.append({
                    "page_number": section_index,
                    "section_title": current_heading,
                    "chunk_text": sec_text,
                    "chunk_type": "text"
                })
                section_index += 1
                current_section_lines = []
            current_heading = txt
            current_section_lines.append(f"### {txt}")
        elif para.style.name.startswith("List"):
            current_section_lines.append(f"- {txt}")
        else:
            current_section_lines.append(txt)

    # Tables in docx
    for i, table in enumerate(doc.tables):
        rows = []
        for row in table.rows:
            cells = [cell.text.replace('\n', ' ').strip() for cell in row.cells]
            rows.append(" | ".join(cells))
        if rows:
            header = "| " + rows[0] + " |"
            col_count = len(rows[0].split(" | "))
            delim = "| " + " | ".join(["---"] * col_count) + " |"
            body = ["| " + r + " |" for r in rows[1:]]
            table_md = "\n" + "\n".join([header, delim] + body) + "\n"
            current_section_lines.append(table_md)

    if current_section_lines:
        sec_text = clean_text("\n".join(current_section_lines))
        text_blocks.append({
            "page_number": section_index,
            "section_title": current_heading,
            "chunk_text": sec_text,
            "chunk_type": "text"
        })

    duration = round(time.time() - start_time, 2)
    combined = "\n\n".join([b["chunk_text"] for b in text_blocks])
    total_pages = max(1, len(text_blocks))
    confidence = calculate_confidence_score(combined, total_pages, False, warnings)

    return {
        "file_type": "DOCX",
        "page_count": total_pages,
        "processed_pages": total_pages,
        "ocr_used": False,
        "extraction_method": "python-docx (Heading & Table Recovery)",
        "duration_seconds": duration,
        "confidence_score": confidence,
        "warnings": warnings,
        "raw_text": combined,
        "blocks": text_blocks
    }

def extract_txt_precision(txt_path: str) -> Dict[str, Any]:
    """Plain text or markdown file reader."""
    start_time = time.time()
    try:
        with open(txt_path, 'r', encoding='utf-8', errors='ignore') as f:
            content = clean_text(f.read())
    except Exception as e:
        content = ""

    blocks = []
    if content:
        # Split into logical paragraphs of ~800 chars
        paragraphs = content.split('\n\n')
        cur_chunk = []
        cur_len = 0
        p_no = 1
        for p in paragraphs:
            if cur_len + len(p) > 800 and cur_chunk:
                blocks.append({
                    "page_number": p_no,
                    "section_title": f"Section {p_no}",
                    "chunk_text": "\n\n".join(cur_chunk),
                    "chunk_type": "text"
                })
                p_no += 1
                cur_chunk = [p]
                cur_len = len(p)
            else:
                cur_chunk.append(p)
                cur_len += len(p)
        if cur_chunk:
            blocks.append({
                "page_number": p_no,
                "section_title": f"Section {p_no}",
                "chunk_text": "\n\n".join(cur_chunk),
                "chunk_type": "text"
            })

    duration = round(time.time() - start_time, 2)
    confidence = calculate_confidence_score(content, max(1, len(blocks)), False, [])

    return {
        "file_type": "TXT",
        "page_count": max(1, len(blocks)),
        "processed_pages": max(1, len(blocks)),
        "ocr_used": False,
        "extraction_method": "Direct UTF-8 Parser",
        "duration_seconds": duration,
        "confidence_score": confidence,
        "warnings": [],
        "raw_text": content,
        "blocks": blocks
    }

def process_document(file_path: str) -> Dict[str, Any]:
    """
    Master entry point for the precision extraction pipeline.
    Routes to the proper extractor and produces structured, verified extraction output.
    """
    if not os.path.exists(file_path):
        raise FileNotFoundError(f"File not found: {file_path}")

    ext = file_path.rsplit(".", 1)[-1].lower()
    if ext == "pdf":
        return extract_pdf_precision(file_path)
    elif ext in ["pptx", "ppt"]:
        return extract_pptx_precision(file_path)
    elif ext == "docx":
        return extract_docx_precision(file_path)
    elif ext in ["txt", "md"]:
        return extract_txt_precision(file_path)
    else:
        raise ValueError(f"Unsupported document format: .{ext}")

# ── Stage F: Sub-chunking for Retrieval ────────────────────────────────────────

def prepare_chunks_for_storage(doc_id: str, user_id: str, blocks: List[Dict[str, Any]], 
                               max_tokens: int = 350, overlap_tokens: int = 40) -> List[Dict[str, Any]]:
    """
    Splits document blocks into page-aware, overlapping retrieval chunks
    guaranteeing section headers and page attribution are preserved.
    """
    chunks = []
    chunk_index = 1

    for block in blocks:
        page_no = block.get("page_number", 1)
        sec_title = block.get("section_title", "General")
        text = block.get("chunk_text", "").strip()
        c_type = block.get("chunk_type", "text")

        words = text.split()
        if not words:
            continue

        if len(words) <= max_tokens:
            chunks.append({
                "id": f"{doc_id}_c{chunk_index}",
                "document_id": doc_id,
                "user_id": user_id,
                "page_number": page_no,
                "section_title": sec_title,
                "chunk_text": text,
                "chunk_type": c_type,
                "token_count": len(words)
            })
            chunk_index += 1
        else:
            # Overlapping split
            stride = max_tokens - overlap_tokens
            for start in range(0, len(words), stride):
                end = min(len(words), start + max_tokens)
                sub_text = " ".join(words[start:end])
                chunks.append({
                    "id": f"{doc_id}_c{chunk_index}",
                    "document_id": doc_id,
                    "user_id": user_id,
                    "page_number": page_no,
                    "section_title": sec_title,
                    "chunk_text": sub_text,
                    "chunk_type": c_type,
                    "token_count": len(sub_text.split())
                })
                chunk_index += 1
                if end >= len(words):
                    break

    return chunks
