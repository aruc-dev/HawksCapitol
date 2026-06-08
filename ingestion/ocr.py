from __future__ import annotations

from io import BytesIO


def ocr_image_bytes(data: bytes) -> tuple[str, float]:
    if not data:
        return "", 0.0
    try:
        from PIL import Image
        import pytesseract
    except Exception:
        return "", 0.0
    try:
        image = Image.open(BytesIO(data))
        text = pytesseract.image_to_string(image).strip()
    except Exception:
        return "", 0.0
    return text, 0.55 if text else 0.0
