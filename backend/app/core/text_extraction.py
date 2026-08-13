"""Best-effort plain-text extraction from an uploaded file's raw bytes.

Only the formats we can reliably read are supported (txt, pdf, docx) — doc,
xlsx, and pptx are legacy/structured formats not worth the added dependency
weight for a single feature, so they're reported as unsupported rather than
guessed at. Any parse failure (corrupted file, scanned/image-only PDF with
no text layer) returns None rather than raising — callers treat "couldn't
extract text" as one uniform outcome regardless of why.
"""
import io

TEXT_EXTRACTABLE_EXTENSIONS = {"txt", "pdf", "docx"}


def extract_text(content: bytes, extension: str) -> str | None:
    ext = extension.lstrip(".").lower()

    if ext == "txt":
        try:
            text = content.decode("utf-8", errors="replace")
            return text if text.strip() else None
        except Exception:
            return None

    if ext == "pdf":
        try:
            from pypdf import PdfReader

            reader = PdfReader(io.BytesIO(content))
            text = "\n".join(page.extract_text() or "" for page in reader.pages)
            return text if text.strip() else None
        except BaseException:
            # BaseException, not Exception: a malformed PDF can trip a panic
            # in pypdf's Rust-backed crypto dependency, which doesn't subclass
            # Exception — a corrupt file must never be able to crash a request.
            return None

    if ext == "docx":
        try:
            from docx import Document

            document = Document(io.BytesIO(content))
            text = "\n".join(p.text for p in document.paragraphs)
            return text if text.strip() else None
        except BaseException:
            return None

    return None
