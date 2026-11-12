import re
from langchain_text_splitters import RecursiveCharacterTextSplitter

# Used only for long runbooks and technical references.
# Prefer a blank line, then a newline, then a sentence, then a space,
# so a cut lands on a boundary when one is close enough.
# Overlap keeps the end of one chunk at the start of the next.
splitter = RecursiveCharacterTextSplitter(
    chunk_size=1800,
    chunk_overlap=180,
    separators=["\n\n", "\n", ". ", " ", ""]
)


def chunk_knowledge_document(
    text: str,
    document_id: str,
    document_type: str
) -> list[dict]:
    """Turn one knowledge document into records ready to index.

    known_issue stays one chunk so the error, evidence, cause, and
    solution are not separated. runbook and technical_reference are
    split on level-2 Markdown headings, then by size if a section is
    still long. Each record keeps the document id, type, order, and text.
    """

    text = text.strip()

    if not text or not document_id.strip():
        raise ValueError("Document content and ID are required")

    if document_type == "known_issue":
        # A short incident is more useful intact than cut into pieces.
        if len(text) > 5000:
            raise ValueError("Known issue exceeds size limit")

        chunks = [text]

    elif document_type in {"runbook", "technical_reference"}:
        # The lookahead keeps each "## " heading with the text under it.
        # Text before the first heading is the introduction.
        sections = re.split(
            r"(?=^##\s)",
            text,
            flags=re.MULTILINE
        )

        introduction = sections[0].strip()

        # Repeat the title on every section so a later chunk still
        # says which guide it came from.
        if len(sections) > 1:
            sections = [
                f"{introduction}\n\n{s.strip()}".strip()
                for s in sections[1:]
                if s.strip()
            ]

        # A guide with no headings is one section and is split by size.
        chunks = []
        for section in sections:
            chunks.extend(splitter.split_text(section))

    else:
        raise ValueError("Unsupported knowledge document type")

    return [
        {
            "document_id": document_id,
            "document_type": document_type,
            "chunk_index": i,
            "content": chunk
        }
        for i, chunk in enumerate(chunks)
    ]
