from __future__ import annotations


def extract_text_from_pdf_bytes(data: bytes) -> tuple[str, float]:
    if not data:
        return "", 0.0
    try:
        text = data.decode("utf-8")
        return text, 0.8
    except UnicodeDecodeError:
        return "", 0.2
