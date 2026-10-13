"""Resume and Job Description document parser supporting PDF, DOCX, and plain text."""

import io
import re
import xml.etree.ElementTree as ET
import zipfile

from backend.context.models import ExtractedDocument
from backend.safety.input_screen import validate_input

COMMON_SECTIONS = [
    "summary",
    "objective",
    "experience",
    "work experience",
    "employment",
    "education",
    "skills",
    "technical skills",
    "projects",
    "certifications",
    "requirements",
    "responsibilities",
    "qualifications",
]


class DocumentParseError(ValueError):
    """Raised when document content cannot be parsed."""

    pass


def _extract_text_from_docx(file_bytes: bytes) -> str:
    """Extract plain text from a DOCX file using standard library zipfile and XML parser."""
    try:
        with zipfile.ZipFile(io.BytesIO(file_bytes)) as docx_zip:
            if "word/document.xml" not in docx_zip.namelist():
                raise DocumentParseError("Invalid DOCX file: missing word/document.xml")
            xml_content = docx_zip.read("word/document.xml")

        root = ET.fromstring(xml_content)
        # XML namespace for WordprocessingML
        ns = {"w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main"}

        paragraphs = []
        for p in root.findall(".//w:p", ns):
            texts = [node.text for node in p.findall(".//w:t", ns) if node.text]
            if texts:
                paragraphs.append("".join(texts))

        return "\n\n".join(paragraphs)
    except Exception as exc:
        raise DocumentParseError(f"Failed to parse DOCX: {exc}") from exc


def _decode_pdf_string(pdf_str: str) -> str:
    """Decode PDF escape sequences (octal escapes and backslash escapes)."""
    # Replace common escapes
    pdf_str = (
        pdf_str.replace(r"\n", "\n")
        .replace(r"\r", "\r")
        .replace(r"\t", "\t")
        .replace(r"\(", "(")
        .replace(r"\)", ")")
        .replace(r"\\", "\\")
    )

    # Replace octal escapes (\ddd)
    def _oct_replace(m: re.Match) -> str:
        try:
            return chr(int(m.group(1), 8))
        except Exception:
            return ""

    pdf_str = re.sub(r"\\([0-7]{1,3})", _oct_replace, pdf_str)
    return pdf_str


def _extract_text_from_pdf_stream(data: bytes) -> str:
    """Extract text operations from PDF stream content."""
    text_chunks: list[str] = []

    # Find text blocks BT ... ET
    bt_blocks = re.findall(rb"BT\s*(.*?)\s*ET", data, re.DOTALL)
    for block in bt_blocks:
        block_str = block.decode("latin-1", errors="ignore")

        # Extract (text) Tj
        for tj_match in re.finditer(r"\((.*?)\)\s*Tj", block_str, re.DOTALL):
            decoded = _decode_pdf_string(tj_match.group(1))
            if decoded:
                text_chunks.append(decoded)

        # Extract [ (...) -10 (...) ] TJ
        for tj_arr_match in re.finditer(r"\[(.*?)\]\s*TJ", block_str, re.DOTALL):
            arr_content = tj_arr_match.group(1)
            parts = re.findall(r"\((.*?)\)", arr_content, re.DOTALL)
            decoded_parts = [_decode_pdf_string(p) for p in parts]
            if decoded_parts:
                text_chunks.append("".join(decoded_parts))

        # Handle ' or " operators if present
        for quote_match in re.finditer(r"\((.*?)\)\s*['\"]", block_str, re.DOTALL):
            decoded = _decode_pdf_string(quote_match.group(1))
            if decoded:
                text_chunks.append(decoded)

    return " ".join(text_chunks)


def _extract_text_from_pdf(file_bytes: bytes) -> str:
    """Extract text from PDF file.

    Tries pypdf if available, falling back to a pure-python stream decoder.
    """
    # Try pypdf first if installed
    try:
        import pypdf

        reader = pypdf.PdfReader(io.BytesIO(file_bytes))
        pages_text = [page.extract_text() or "" for page in reader.pages]
        full_text = "\n\n".join(pages_text).strip()
        if full_text:
            return full_text
    except ImportError:
        pass
    except Exception:
        pass

    # Pure Python PDF stream extractor
    import zlib

    extracted_parts: list[str] = []

    # Look for all stream ... endstream blocks
    for stream_match in re.finditer(rb"stream\r?\n(.*?)\r?\nendstream", file_bytes, re.DOTALL):
        raw_stream = stream_match.group(1)
        # Try zlib decompress (FlateDecode)
        stream_data = None
        try:
            stream_data = zlib.decompress(raw_stream)
        except Exception:
            # Maybe raw uncompressed stream
            stream_data = raw_stream

        if stream_data:
            text = _extract_text_from_pdf_stream(stream_data)
            if text:
                extracted_parts.append(text)

    # Fallback to direct raw scan if stream extraction yielded empty
    if not extracted_parts:
        text = _extract_text_from_pdf_stream(file_bytes)
        if text:
            extracted_parts.append(text)

    result = "\n".join(extracted_parts).strip()
    if not result:
        # Check for simple plain text embedded in PDF
        cleaned = re.sub(rb"[^\x20-\x7e\n\r\t]", b"", file_bytes).decode("latin-1")
        lines = [line.strip() for line in cleaned.splitlines() if len(line.strip()) > 15]
        result = "\n".join(lines).strip()

    if not result:
        raise DocumentParseError("Could not extract any text from PDF file.")

    return result


def _split_into_sections(text: str) -> dict[str, str]:
    """Detect common resume/JD section headings and split text accordingly."""
    sections: dict[str, str] = {}
    lines = text.splitlines()

    current_section = "general"
    current_lines: list[str] = []

    # Pattern matching section headers like "EXPERIENCE:", "## Skills", "WORK EXPERIENCE"
    header_pattern = re.compile(
        r"^(?:#{1,3}\s*)?([A-Za-z\s]{3,30})(?:\s*:)?\s*$",
        re.IGNORECASE,
    )

    for line in lines:
        stripped = line.strip()
        match = header_pattern.match(stripped)
        if match:
            candidate = match.group(1).strip().lower()
            if candidate in COMMON_SECTIONS or any(s in candidate for s in COMMON_SECTIONS):
                if current_lines:
                    sections[current_section] = "\n".join(current_lines).strip()
                    current_lines = []
                current_section = candidate
                continue
        current_lines.append(line)

    if current_lines:
        sections[current_section] = "\n".join(current_lines).strip()

    return {k: v for k, v in sections.items() if v}


def parse_document(
    content: bytes | str,
    filename: str | None = None,
    field_name: str = "resume",
) -> ExtractedDocument:
    """Parse document bytes or text into a sanitized ExtractedDocument.

    Supports:
        - Plain text (.txt, raw string, markdown)
        - PDF (.pdf)
        - DOCX (.docx)

    Raises:
        DocumentParseError: If file is corrupted or unsupported format.
        InputTooLongError: If extracted text exceeds safety limits.
    """
    raw_text = ""
    lower_fn = (filename or "").lower()

    if isinstance(content, str):
        raw_text = content
    elif lower_fn.endswith(".docx") or content.startswith(b"PK\x03\x04"):
        raw_text = _extract_text_from_docx(content)
    elif lower_fn.endswith(".pdf") or content.startswith(b"%PDF-"):
        raw_text = _extract_text_from_pdf(content)
    else:
        # Default treat as UTF-8 or Latin-1 text
        try:
            raw_text = content.decode("utf-8")
        except UnicodeDecodeError:
            try:
                raw_text = content.decode("latin-1")
            except Exception as exc:
                raise DocumentParseError(f"Unsupported document format: {exc}") from exc

    # Sanitize and normalize using safety module
    sanitized = validate_input(raw_text, field_name=field_name)
    sections = _split_into_sections(sanitized)

    return ExtractedDocument(
        text=sanitized,
        filename=filename,
        char_count=len(sanitized),
        sections=sections,
    )
