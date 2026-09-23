from io import BytesIO
from pypdf import PdfReader

MAX_FILE_BYTES = 10 * 1024 * 1024
MAX_TEXT_CHARS = 50_000

class DocumentError(ValueError):
    pass

def extract_text(filename: str, data: bytes) -> tuple[str, str]:
    if not data or len(data) > MAX_FILE_BYTES:
        raise DocumentError("Файл должен быть непустым и не больше 10 МБ")
    if filename.lower().endswith(".txt"):
        for encoding in ("utf-8-sig", "cp1251"):
            try:
                text = data.decode(encoding)
                break
            except UnicodeDecodeError:
                continue
        else:
            raise DocumentError("Не удалось прочитать текстовый файл")
        mime_type = "text/plain"
    elif filename.lower().endswith(".pdf"):
        if not data.startswith(b"%PDF-"):
            raise DocumentError("Неверный формат PDF")
        try:
            reader = PdfReader(BytesIO(data))
            if len(reader.pages) > 100:
                raise DocumentError("Допускается не более 100 страниц")
            text = "\n".join(page.extract_text() or "" for page in reader.pages)
        except DocumentError:
            raise
        except Exception as exc:
            raise DocumentError("Не удалось прочитать PDF") from exc
        mime_type = "application/pdf"
    else:
        raise DocumentError("Поддерживаются только TXT и PDF")
    text = text.strip()
    if not text:
        raise DocumentError("В файле нет извлекаемого текста; скан требует OCR")
    if len(text) > MAX_TEXT_CHARS:
        raise DocumentError("Извлечённый текст слишком длинный")
    return text, mime_type
