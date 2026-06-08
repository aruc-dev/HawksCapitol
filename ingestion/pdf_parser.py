from __future__ import annotations

from io import BytesIO
import re

from ingestion.ocr import ocr_image_bytes


def extract_text_from_pdf_bytes(data: bytes) -> tuple[str, float]:
    if not data:
        return "", 0.0
    for extractor in (_extract_with_pypdf, _extract_with_pdfplumber):
        text = extractor(data)
        if text:
            return text, 0.9
    text = _extract_literal_pdf_strings(data)
    if text:
        return text, 0.65
    try:
        text = data.decode("utf-8").strip()
        if text:
            return text, 0.8
    except UnicodeDecodeError:
        pass
    try:
        text = data.decode("latin-1").strip()
        if text and "%PDF" not in text[:20]:
            return text, 0.55
    except UnicodeDecodeError:
        pass
    ocr_text, ocr_confidence = ocr_image_bytes(data)
    return ocr_text, ocr_confidence


def _extract_with_pypdf(data: bytes) -> str:
    try:
        from pypdf import PdfReader
    except Exception:
        return ""
    try:
        reader = PdfReader(BytesIO(data))
        pages = [(page.extract_text() or "").strip() for page in reader.pages]
    except Exception:
        return ""
    return "\n".join(page for page in pages if page).strip()


def _extract_with_pdfplumber(data: bytes) -> str:
    try:
        import pdfplumber
    except Exception:
        return ""
    try:
        with pdfplumber.open(BytesIO(data)) as pdf:
            pages = [(page.extract_text() or "").strip() for page in pdf.pages]
    except Exception:
        return ""
    return "\n".join(page for page in pages if page).strip()


def _extract_literal_pdf_strings(data: bytes) -> str:
    try:
        raw = data.decode("latin-1")
    except UnicodeDecodeError:
        return ""
    if "%PDF" not in raw[:1024]:
        return ""
    chunks = []
    for match in re.finditer(r"\((?:\\.|[^\\()])*\)\s*T[jJ]", raw, flags=re.DOTALL):
        literal = match.group(0).rsplit(")", 1)[0][1:]
        chunks.append(_unescape_pdf_literal(literal))
    array_matches = re.finditer(r"\[(.*?)\]\s*TJ", raw, flags=re.DOTALL)
    for match in array_matches:
        for literal in re.findall(r"\((?:\\.|[^\\()])*\)", match.group(1), flags=re.DOTALL):
            chunks.append(_unescape_pdf_literal(literal[1:-1]))
    return "\n".join(part.strip() for part in chunks if part.strip())


def _unescape_pdf_literal(value: str) -> str:
    value = value.replace(r"\(", "(").replace(r"\)", ")").replace(r"\\", "\\")
    value = value.replace(r"\n", "\n").replace(r"\r", "\n").replace(r"\t", "\t")
    return value
