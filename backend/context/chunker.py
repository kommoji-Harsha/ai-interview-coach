"""Document chunking utility for semantic embedding and retrieval."""

import re
import uuid

from backend.context.models import DocumentChunk


def _split_into_paragraphs_or_sentences(text: str) -> list[str]:
    """Split text into units (paragraphs first, then sentences)."""
    # First split by double newlines
    paragraphs = [p.strip() for p in text.split("\n\n") if p.strip()]
    if not paragraphs:
        paragraphs = [text.strip()]

    units: list[str] = []
    for para in paragraphs:
        if len(para) <= 600:
            units.append(para)
        else:
            # Split paragraph into sentences
            sentences = re.split(r"(?<=[.!?])\s+", para)
            units.extend([s.strip() for s in sentences if s.strip()])

    return units


def chunk_text(
    text: str,
    document_id: uuid.UUID,
    document_type: str,
    chunk_size: int = 500,
    chunk_overlap: int = 100,
    sections: dict[str, str] | None = None,
) -> list[DocumentChunk]:
    """Split document text into overlapping semantic chunks with section attribution.

    Args:
        text: Full document plain text.
        document_id: UUID of parent resume or JD.
        document_type: 'resume' or 'jd'.
        chunk_size: Target maximum characters per chunk.
        chunk_overlap: Number of characters to overlap between consecutive chunks.
        sections: Optional mapping of section names to section text.

    Returns:
        List of DocumentChunk instances.
    """
    if not text.strip():
        return []

    chunks: list[DocumentChunk] = []
    chunk_index = 0

    if sections and len(sections) > 1:
        # Section-aware chunking
        for sec_name, sec_content in sections.items():
            if not sec_content.strip():
                continue

            sec_start = text.find(sec_content)
            if sec_start == -1:
                sec_start = 0

            units = _split_into_paragraphs_or_sentences(sec_content)
            current_buffer: list[str] = []
            current_len = 0
            rel_offset = 0

            for unit in units:
                if current_len + len(unit) > chunk_size and current_buffer:
                    chunk_text_str = "\n".join(current_buffer)
                    chunk_start = sec_start + rel_offset
                    chunk_end = chunk_start + len(chunk_text_str)

                    chunks.append(
                        DocumentChunk(
                            document_id=document_id,
                            document_type=document_type,
                            chunk_index=chunk_index,
                            content=chunk_text_str,
                            section=sec_name,
                            char_start=chunk_start,
                            char_end=chunk_end,
                            metadata={"word_count": len(chunk_text_str.split())},
                        )
                    )
                    chunk_index += 1

                    # Retain overlap from end of current buffer
                    overlap_units = []
                    overlap_len = 0
                    for prev_u in reversed(current_buffer):
                        if overlap_len + len(prev_u) <= chunk_overlap:
                            overlap_units.insert(0, prev_u)
                            overlap_len += len(prev_u)
                        else:
                            break

                    current_buffer = list(overlap_units)
                    current_len = sum(len(u) for u in current_buffer)
                    rel_offset = (
                        sec_content.find(unit, rel_offset) if unit in sec_content else rel_offset
                    )

                current_buffer.append(unit)
                current_len += len(unit)

            if current_buffer:
                chunk_text_str = "\n".join(current_buffer)
                chunk_start = sec_start + rel_offset
                chunk_end = chunk_start + len(chunk_text_str)

                chunks.append(
                    DocumentChunk(
                        document_id=document_id,
                        document_type=document_type,
                        chunk_index=chunk_index,
                        content=chunk_text_str,
                        section=sec_name,
                        char_start=chunk_start,
                        char_end=chunk_end,
                        metadata={"word_count": len(chunk_text_str.split())},
                    )
                )
                chunk_index += 1
    else:
        # Standard sliding window chunking across text
        units = _split_into_paragraphs_or_sentences(text)
        current_buffer: list[str] = []
        current_len = 0
        running_pos = 0

        for unit in units:
            if current_len + len(unit) > chunk_size and current_buffer:
                chunk_text_str = "\n".join(current_buffer)
                pos = text.find(chunk_text_str[: min(50, len(chunk_text_str))], running_pos)
                if pos == -1:
                    pos = running_pos
                chunk_start = pos
                chunk_end = pos + len(chunk_text_str)
                running_pos = max(
                    running_pos, chunk_start + max(1, len(chunk_text_str) - chunk_overlap)
                )

                chunks.append(
                    DocumentChunk(
                        document_id=document_id,
                        document_type=document_type,
                        chunk_index=chunk_index,
                        content=chunk_text_str,
                        char_start=chunk_start,
                        char_end=chunk_end,
                        metadata={"word_count": len(chunk_text_str.split())},
                    )
                )
                chunk_index += 1

                # Overlap
                overlap_units = []
                overlap_len = 0
                for prev_u in reversed(current_buffer):
                    if overlap_len + len(prev_u) <= chunk_overlap:
                        overlap_units.insert(0, prev_u)
                        overlap_len += len(prev_u)
                    else:
                        break

                current_buffer = list(overlap_units)
                current_len = sum(len(u) for u in current_buffer)

            current_buffer.append(unit)
            current_len += len(unit)

        if current_buffer:
            chunk_text_str = "\n".join(current_buffer)
            pos = text.find(chunk_text_str[: min(50, len(chunk_text_str))], running_pos)
            if pos == -1:
                pos = running_pos
            chunk_start = pos
            chunk_end = pos + len(chunk_text_str)

            chunks.append(
                DocumentChunk(
                    document_id=document_id,
                    document_type=document_type,
                    chunk_index=chunk_index,
                    content=chunk_text_str,
                    char_start=chunk_start,
                    char_end=chunk_end,
                    metadata={"word_count": len(chunk_text_str.split())},
                )
            )

    return chunks
