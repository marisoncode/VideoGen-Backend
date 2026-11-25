import os
import re
import io
import csv
import requests
from typing import Optional, List, Dict, Any

class DocumentService:
    """
    Universal Document, Spreadsheet & Live Google Docs/Sheets Ingestion Service:
    Extracts text and structured scene content from:
      - PDF documents (.pdf)
      - Word documents (.docx, .doc)
      - Excel spreadsheets (.xlsx, .xls)
      - CSV spreadsheets (.csv)
      - Plain text & markdown files (.txt, .md)
      - Live Google Docs URLs (https://docs.google.com/document/d/...)
      - Live Google Sheets URLs (https://docs.google.com/spreadsheets/d/...)
    """

    @classmethod
    def extract_text_from_pdf(cls, file_bytes: bytes) -> str:
        """Extracts text from PDF bytes using pypdf with page markers, or native stream parsing."""
        extracted_text = []

        # 1. Try pypdf with page annotations
        try:
            import pypdf
            reader = pypdf.PdfReader(io.BytesIO(file_bytes))
            for page_idx, page in enumerate(reader.pages):
                text = page.extract_text()
                if text and text.strip():
                    page_num = page_idx + 1
                    extracted_text.append(f"[Page {page_num}]\n{text.strip()}")
            if extracted_text:
                return "\n\n".join(extracted_text)
        except Exception as e:
            print(f"[DocumentService] pypdf notice: {e}, attempting raw stream extraction.")

        # 2. Fallback: Parse visible ASCII text streams from PDF bytes
        try:
            content = file_bytes.decode("latin1", errors="ignore")
            matches = re.findall(r'BT\s*(.*?)\s*ET', content, re.DOTALL)
            for m in matches:
                strings = re.findall(r'\((.*?)\)', m)
                line = " ".join(s.strip() for s in strings if s.strip() and not s.startswith("\\"))
                if len(line) > 5:
                    extracted_text.append(line)
            if extracted_text:
                return "\n".join(extracted_text)
        except Exception as ex:
            print(f"[DocumentService] Raw PDF extraction error: {ex}")

        return ""

    @classmethod
    def extract_text_from_docx(cls, file_bytes: bytes) -> str:
        """Extracts text from Microsoft Word (.docx) files."""
        # 1. Try python-docx
        try:
            import docx
            doc = docx.Document(io.BytesIO(file_bytes))
            paragraphs = [p.text.strip() for p in doc.paragraphs if p.text.strip()]
            for table in doc.tables:
                for row in table.rows:
                    cells = [c.text.strip() for c in row.cells if c.text.strip()]
                    if cells:
                        paragraphs.append(" | ".join(cells))
            if paragraphs:
                return "\n\n".join(paragraphs)
        except Exception as e:
            print(f"[DocumentService] python-docx notice: {e}, trying xml zip fallback.")

        # 2. Fallback: parse word/document.xml inside zip
        try:
            import zipfile
            import xml.etree.ElementTree as ET
            with zipfile.ZipFile(io.BytesIO(file_bytes)) as z:
                xml_content = z.read("word/document.xml")
                tree = ET.fromstring(xml_content)
                text_nodes = tree.iter("{http://schemas.openxmlformats.org/wordprocessingml/2006/main}t")
                text = "".join(n.text for n in text_nodes if n.text)
                if text.strip():
                    return text.strip()
        except Exception as ex:
            print(f"[DocumentService] Docx XML fallback error: {ex}")

        return ""

    @classmethod
    def extract_text_from_xlsx(cls, file_bytes: bytes) -> str:
        """Extracts text and tabular scene data from Excel spreadsheets (.xlsx)."""
        try:
            import openpyxl
            wb = openpyxl.load_workbook(io.BytesIO(file_bytes), data_only=True)
            lines = []

            for sheetname in wb.sheetnames:
                ws = wb[sheetname]
                rows = list(ws.iter_rows(values_only=True))
                if not rows:
                    continue

                # Check if first row is a header like Scene, Title, Narration
                header = [str(c).strip() if c is not None else "" for c in rows[0]]
                is_scene_table = any("scene" in h.lower() or "narration" in h.lower() or "script" in h.lower() for h in header)

                if is_scene_table and len(rows) > 1:
                    for idx, row in enumerate(rows[1:]):
                        row_vals = [str(c).strip() for c in row if c is not None and str(c).strip()]
                        if row_vals:
                            lines.append(f"Scene {idx+1}: " + " — ".join(row_vals))
                else:
                    for row in rows:
                        row_vals = [str(c).strip() for c in row if c is not None and str(c).strip()]
                        if row_vals:
                            lines.append(" | ".join(row_vals))

            return "\n\n".join(lines)
        except Exception as e:
            print(f"[DocumentService] Excel extraction error: {e}")
            return ""

    @classmethod
    def extract_text_from_csv(cls, file_bytes: bytes) -> str:
        """Extracts text from CSV spreadsheets."""
        try:
            content = file_bytes.decode("utf-8", errors="ignore")
            reader = csv.reader(io.StringIO(content))
            rows = [r for r in reader if any(cell.strip() for cell in r)]
            if not rows:
                return ""

            lines = []
            header = [c.strip().lower() for c in rows[0]]
            is_scene_table = any("scene" in h or "narration" in h or "script" in h for h in header)

            if is_scene_table and len(rows) > 1:
                for idx, r in enumerate(rows[1:]):
                    cells = [c.strip() for c in r if c.strip()]
                    if cells:
                        lines.append(f"Scene {idx+1}: " + " — ".join(cells))
            else:
                for r in rows:
                    cells = [c.strip() for c in r if c.strip()]
                    if cells:
                        lines.append(" | ".join(cells))

            return "\n\n".join(lines)
        except Exception as e:
            print(f"[DocumentService] CSV extraction error: {e}")
            return ""

    @classmethod
    def fetch_live_google_doc(cls, url: str) -> str:
        """
        Fetches live text from a shared Google Docs link.
        Supports: https://docs.google.com/document/d/{doc_id}/...
        """
        m = re.search(r'/document/d/([a-zA-Z0-9-_]+)', url)
        if not m:
            raise ValueError("Invalid Google Docs link. Please provide a valid URL like: https://docs.google.com/document/d/.../edit")

        doc_id = m.group(1)
        export_url = f"https://docs.google.com/document/d/{doc_id}/export?format=txt"

        headers = {"User-Agent": "Mozilla/5.0"}
        res = requests.get(export_url, headers=headers, timeout=20)
        if res.status_code == 200 and len(res.content) > 10:
            return cls.clean_text(res.content.decode("utf-8", errors="ignore"))
        elif res.status_code == 404:
            raise ValueError("Google Doc not found. Please ensure link sharing is set to 'Anyone with the link can view'.")
        else:
            # Fallback: scrape visible text from doc view
            view_url = f"https://docs.google.com/document/d/{doc_id}/preview"
            v_res = requests.get(view_url, headers=headers, timeout=20)
            if v_res.status_code == 200:
                plain = re.sub(r'<[^>]+>', ' ', v_res.text)
                return cls.clean_text(plain)
            raise ValueError(f"Could not read Google Doc (HTTP {res.status_code}). Please make sure it is publicly shared.")

    @classmethod
    def fetch_live_google_sheet(cls, url: str) -> str:
        """
        Fetches live tabular scenes from a shared Google Sheets link.
        Supports: https://docs.google.com/spreadsheets/d/{sheet_id}/...
        """
        m = re.search(r'/spreadsheets/d/([a-zA-Z0-9-_]+)', url)
        if not m:
            raise ValueError("Invalid Google Sheets link. Please provide a valid URL like: https://docs.google.com/spreadsheets/d/.../edit")

        sheet_id = m.group(1)
        # Try gviz CSV export endpoint
        export_url = f"https://docs.google.com/spreadsheets/d/{sheet_id}/gviz/tq?tqx=out:csv"

        headers = {"User-Agent": "Mozilla/5.0"}
        res = requests.get(export_url, headers=headers, timeout=20)
        if res.status_code == 200 and len(res.content) > 10:
            return cls.extract_text_from_csv(res.content)

        # Fallback to standard export
        alt_url = f"https://docs.google.com/spreadsheets/d/{sheet_id}/export?format=csv"
        alt_res = requests.get(alt_url, headers=headers, timeout=20)
        if alt_res.status_code == 200 and len(alt_res.content) > 10:
            return cls.extract_text_from_csv(alt_res.content)

        raise ValueError(f"Could not read Google Sheet. Please ensure link sharing is set to 'Anyone with the link can view'.")

    @classmethod
    def parse_uploaded_file(cls, file_bytes: bytes, filename: str) -> str:
        """Automatically detects file type by extension and extracts clean content."""
        ext = os.path.splitext(filename)[1].lower()

        if ext == ".pdf":
            raw = cls.extract_text_from_pdf(file_bytes)
        elif ext in [".docx", ".doc"]:
            raw = cls.extract_text_from_docx(file_bytes)
        elif ext in [".xlsx", ".xls"]:
            raw = cls.extract_text_from_xlsx(file_bytes)
        elif ext == ".csv":
            raw = cls.extract_text_from_csv(file_bytes)
        else:
            try:
                raw = file_bytes.decode("utf-8")
            except Exception:
                raw = file_bytes.decode("latin1", errors="ignore")

        return cls.clean_text(raw)

    @classmethod
    def extract_topic_section(cls, full_text: str, chapter_topic: Optional[str] = None, max_chars: int = 12000) -> str:
        """
        Locates and extracts the relevant chapter or topic content from a potentially long textbook.
        Preserves page markers [Page X] and factual explanations.
        """
        if not full_text or len(full_text) <= max_chars:
            return full_text

        if not chapter_topic or not chapter_topic.strip():
            # If no specific chapter/topic requested, return the first max_chars of content
            return full_text[:max_chars]

        topic = chapter_topic.strip()
        # 1. Search for explicit Chapter/Unit header matching topic or chapter number
        patterns = [
            rf'(?i)(?:Chapter|Unit|Lesson|Topic)\s*[:\-\s]*{re.escape(topic)}',
            rf'(?i)\b{re.escape(topic)}\b'
        ]

        match_start = -1
        for pat in patterns:
            m = re.search(pat, full_text)
            if m:
                match_start = m.start()
                break

        if match_start != -1:
            # Include preceding page marker if nearby (within 300 chars)
            pre_text = full_text[:match_start]
            last_page = pre_text.rfind("[Page ")
            start_pos = last_page if last_page != -1 and (match_start - last_page) < 300 else match_start
            extracted = full_text[start_pos:start_pos + max_chars]
            print(f"[DocumentService] Extracted {len(extracted)} chars for topic '{topic}' starting at char {start_pos}")
            return extracted

        print(f"[DocumentService] Topic '{topic}' not found as explicit header; returning top section of document.")
        return full_text[:max_chars]

    @classmethod
    def clean_text(cls, raw_text: str) -> str:
        """Cleans and normalizes extracted text while preserving page tags."""
        text = re.sub(r'\r\n|\r', '\n', raw_text)
        text = re.sub(r'[ \t]+', ' ', text)
        text = re.sub(r'\n{3,}', '\n\n', text)
        return text.strip()

document_service = DocumentService()
