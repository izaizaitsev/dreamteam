"""Bounded, deterministic extraction of text in DOCX reading order."""
from io import BytesIO
from zipfile import BadZipFile, ZipFile
from xml.etree import ElementTree as ET

MAX_BYTES = 10 * 1024 * 1024
MAX_UNCOMPRESSED = 40 * 1024 * 1024
MAX_ENTRIES = 1000
W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"

class InvalidDocx(ValueError):
    pass

def extract(raw: bytes) -> list[tuple[str, str]]:
    if not raw or len(raw) > MAX_BYTES:
        raise InvalidDocx("DOCX должен быть непустым и не больше 10 МБ")
    try:
        with ZipFile(BytesIO(raw)) as archive:
            names = archive.namelist()
            if "word/document.xml" not in names or "[Content_Types].xml" not in names:
                raise InvalidDocx("Файл не является DOCX")
            if len(names) > MAX_ENTRIES or sum(item.file_size for item in archive.infolist()) > MAX_UNCOMPRESSED:
                raise InvalidDocx("DOCX превышает ограничения распаковки")
            for item in archive.infolist():
                if item.compress_size and item.file_size > item.compress_size * 100:
                    raise InvalidDocx("Подозрительное сжатие DOCX")
                lower = item.filename.lower()
                if "vbaproject" in lower or lower.startswith("word/embeddings/"):
                    raise InvalidDocx("Встроенные объекты и макросы не поддерживаются")
                if lower.endswith(".rels"):
                    relations = archive.read(item)
                    if b'TargetMode="External"' in relations or b"TargetMode='External'" in relations:
                        raise InvalidDocx("Внешние связи DOCX не поддерживаются")
            xml = archive.read("word/document.xml")
            if b"<!DOCTYPE" in xml.upper() or b"<!ENTITY" in xml.upper():
                raise InvalidDocx("DTD и сущности XML не поддерживаются")
            root = ET.fromstring(xml)
    except (BadZipFile, KeyError, ET.ParseError) as exc:
        raise InvalidDocx("Повреждённый DOCX") from exc
    body = root.find(f"{W}body")
    if body is None:
        raise InvalidDocx("В DOCX нет основного текста")
    passages: list[tuple[str, str]] = []
    section = "Основной текст"
    for element in body:
        paragraphs = [element] if element.tag == f"{W}p" else list(element.iter(f"{W}p")) if element.tag == f"{W}tbl" else []
        for paragraph in paragraphs:
            pieces = []
            for node in paragraph.iter():
                if node.tag == f"{W}t" and node.text:
                    pieces.append(node.text)
                elif node.tag == f"{W}tab":
                    pieces.append("\t")
                elif node.tag == f"{W}br":
                    pieces.append("\n")
            content = "".join(pieces).strip()
            if not content:
                continue
            style = paragraph.find(f"{W}pPr/{W}pStyle")
            style_name = style.get(f"{W}val", "") if style is not None else ""
            if style_name.lower().startswith("heading") or content.lower().startswith(("статья ", "раздел ", "глава ")):
                section = content[:300]
            passages.append((section, content))
    if not passages:
        raise InvalidDocx("В DOCX нет извлекаемого текста")
    if sum(len(text) for _, text in passages) > 200_000:
        raise InvalidDocx("Извлечённый текст слишком длинный")
    return passages

