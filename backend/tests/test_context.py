"""Comprehensive unit tests for context parsing, chunking, embeddings, pgvector retrieval, and skill-gap analysis."""

import io
import uuid
import xml.etree.ElementTree as ET
import zipfile

import pytest

from backend.context.chunker import chunk_text
from backend.context.embeddings import (
    DeterministicEmbeddingService,
)
from backend.context.models import DocumentChunk, ResumeContext
from backend.context.parser import parse_document
from backend.context.pgvector_provider import PgVectorContextProvider, cosine_similarity
from backend.context.skill_gap import analyze_skill_gap

# ---------------------------------------------------------------------------
# Helper: Synthetic DOCX and PDF byte builders
# ---------------------------------------------------------------------------


def create_synthetic_docx_bytes(paragraphs: list[str]) -> bytes:
    """Build a valid minimal in-memory DOCX file."""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        # Create minimal word/document.xml
        root = ET.Element("{http://schemas.openxmlformats.org/wordprocessingml/2006/main}document")
        body = ET.SubElement(
            root, "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}body"
        )
        for p_text in paragraphs:
            p = ET.SubElement(
                body, "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}p"
            )
            r = ET.SubElement(p, "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}r")
            t = ET.SubElement(r, "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}t")
            t.text = p_text

        xml_str = ET.tostring(root, encoding="utf-8")
        zf.writestr("word/document.xml", xml_str)

    return buf.getvalue()


def create_synthetic_pdf_bytes(lines: list[str]) -> bytes:
    """Build a minimal in-memory PDF with stream text content."""
    stream_content = "BT\n/F1 12 Tf\n"
    for line in lines:
        stream_content += f"({line}) Tj\n"
    stream_content += "ET\n"

    pdf_text = (
        "%PDF-1.4\n"
        "1 0 obj\n<< /Type /Catalog /Pages 2 0 R >>\nendobj\n"
        "2 0 obj\n<< /Type /Pages /Kids [3 0 R] /Count 1 >>\nendobj\n"
        "3 0 obj\n<< /Type /Page /Parent 2 0 R /Contents 4 0 R >>\nendobj\n"
        f"4 0 obj\n<< /Length {len(stream_content)} >>\n"
        f"stream\n{stream_content}endstream\nendobj\n"
        "xref\n0 5\n"
        "trailer\n<< /Root 1 0 R >>\n%%EOF"
    )
    return pdf_text.encode("latin-1")


# ---------------------------------------------------------------------------
# Parser Tests
# ---------------------------------------------------------------------------


def test_parse_plain_text():
    sample = (
        "SUMMARY\nExperienced Python and FastAPI backend engineer.\n\n"
        "EXPERIENCE\nBuilt high throughput APIs at ScaleCorp for 4 years.\n\n"
        "SKILLS\nPython, Docker, PostgreSQL, Redis."
    )
    doc = parse_document(sample, filename="resume.txt")
    assert doc.char_count == len(sample)
    assert "experience" in doc.sections
    assert "Built high throughput APIs" in doc.sections["experience"]


def test_parse_docx():
    docx_bytes = create_synthetic_docx_bytes(
        [
            "Jane Doe - Software Engineer",
            "EXPERIENCE",
            "Senior Backend Engineer at TechCorp leading microservices migration.",
            "SKILLS",
            "Python, AWS, Kubernetes, PostgreSQL",
        ]
    )
    doc = parse_document(docx_bytes, filename="resume.docx")
    assert "Jane Doe" in doc.text
    assert "TechCorp" in doc.text
    assert doc.char_count > 50


def test_parse_pdf():
    pdf_bytes = create_synthetic_pdf_bytes(
        [
            "Alice Smith - Distributed Systems Engineer",
            "EXPERIENCE: 5 years designing distributed storage systems",
            "SKILLS: Go, Python, gRPC, PostgreSQL",
        ]
    )
    doc = parse_document(pdf_bytes, filename="resume.pdf")
    assert "Alice Smith" in doc.text
    assert "distributed storage" in doc.text


# ---------------------------------------------------------------------------
# Chunker Tests
# ---------------------------------------------------------------------------


def test_chunk_text_sliding_window():
    doc_id = uuid.uuid4()
    text = (
        "Sentence one about engineering. " * 15
        + "\n\n"
        + "Sentence two about database systems. " * 15
        + "\n\n"
        + "Sentence three about architecture. " * 15
    )
    chunks = chunk_text(
        text, document_id=doc_id, document_type="resume", chunk_size=300, chunk_overlap=50
    )

    assert len(chunks) >= 3
    for i, c in enumerate(chunks):
        assert c.document_id == doc_id
        assert c.chunk_index == i
        assert len(c.content) > 0
        assert c.char_end > c.char_start


def test_chunk_text_with_sections():
    doc_id = uuid.uuid4()
    full_text = (
        "SUMMARY:\nSenior Backend Developer with 6 years experience.\n\n"
        "EXPERIENCE:\nLed migration of monolith to microservices using Python and Kafka.\n\n"
        "SKILLS:\nPython, Docker, PostgreSQL, Redis."
    )
    sections = {
        "summary": "Senior Backend Developer with 6 years experience.",
        "experience": "Led migration of monolith to microservices using Python and Kafka.",
        "skills": "Python, Docker, PostgreSQL, Redis.",
    }
    chunks = chunk_text(full_text, document_id=doc_id, document_type="resume", sections=sections)

    assert len(chunks) == 3
    section_names = [c.section for c in chunks]
    assert "summary" in section_names
    assert "experience" in section_names
    assert "skills" in section_names


# ---------------------------------------------------------------------------
# Embedding and Vector Similarity Tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_deterministic_embedding_service():
    embedder = DeterministicEmbeddingService(dimension=1536)

    vec1 = await embedder.embed_text("Senior Python Developer with PostgreSQL expertise")
    vec2 = await embedder.embed_text("Senior Python Engineer with Postgres database knowledge")
    vec3 = await embedder.embed_text("Pediatric nurse with emergency triage clinical background")

    assert len(vec1) == 1536
    assert len(vec2) == 1536

    sim_related = cosine_similarity(vec1, vec2)
    sim_unrelated = cosine_similarity(vec1, vec3)

    assert sim_related > 0.4
    assert sim_related > sim_unrelated


# ---------------------------------------------------------------------------
# ContextProvider and Semantic Retrieval Tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_pgvector_context_provider_store_and_retrieve():
    provider = PgVectorContextProvider()
    user_id = uuid.uuid4()
    resume_id = uuid.uuid4()

    chunks = [
        DocumentChunk(
            document_id=resume_id,
            document_type="resume",
            chunk_index=0,
            content="Built scalable microservices using FastAPI, Python, and Redis caching.",
            section="experience",
        ),
        DocumentChunk(
            document_id=resume_id,
            document_type="resume",
            chunk_index=1,
            content="Managed continuous deployment pipelines with Docker and GitHub Actions.",
            section="devops",
        ),
        DocumentChunk(
            document_id=resume_id,
            document_type="resume",
            chunk_index=2,
            content="Graduated from State University with Bachelor of Science in Mathematics.",
            section="education",
        ),
    ]

    resume_context = ResumeContext(
        id=resume_id,
        user_id=user_id,
        filename="resume.pdf",
        raw_text="\n\n".join(c.content for c in chunks),
        char_count=sum(len(c.content) for c in chunks),
        chunks=chunks,
    )

    await provider.store_resume_context(resume_context)

    # Verify retrieval by semantic query
    results = await provider.retrieve_relevant_context(
        query="FastAPI python redis cache",
        resume_id=resume_id,
        top_k=2,
    )

    assert len(results) == 2
    assert "FastAPI" in results[0].content

    # Verify deletion
    await provider.delete_resume_context(resume_id)
    assert await provider.get_resume_context(resume_id) is None


# ---------------------------------------------------------------------------
# Skill Gap Analysis Tests
# ---------------------------------------------------------------------------


def test_analyze_skill_gap_high_match():
    resume_text = (
        "Senior Backend Engineer with 6 years experience in Python, FastAPI, and PostgreSQL. "
        "Experienced in Docker containerization, Redis caching, and automated testing with pytest."
    )
    jd_text = (
        "We are looking for a Senior Python Developer.\n"
        "Requirements:\n"
        "- Strong proficiency in Python and FastAPI\n"
        "- Experience with PostgreSQL database design\n"
        "- Containerization with Docker\n"
        "- Unit and integration testing"
    )

    report = analyze_skill_gap(resume_text, jd_text, role_title="Senior Python Developer")

    assert report.match_score >= 0.75
    assert "python" in report.matched_skills
    assert "fastapi" in report.matched_skills
    assert "postgresql" in report.matched_skills
    assert len(report.details) > 0
    assert len(report.recommendations) > 0


def test_analyze_skill_gap_low_match():
    resume_text = (
        "Frontend Designer specializing in Figma, UI/UX wireframing, and CSS animations. "
        "Experience creating web marketing landing pages."
    )
    jd_text = (
        "Kubernetes Infrastructure Engineer.\n"
        "Requirements:\n"
        "- 5+ years with Kubernetes container orchestration\n"
        "- Kafka streaming pipelines\n"
        "- Go / gRPC services\n"
        "- Linux kernel tuning"
    )

    report = analyze_skill_gap(resume_text, jd_text, role_title="Infrastructure Engineer")

    assert report.match_score <= 0.4
    assert len(report.missing_skills) >= 2
    assert any("missing key requirements" in rec.lower() for rec in report.recommendations)
