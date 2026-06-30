import asyncio
from pathlib import Path
from typing import List
from dataclasses import dataclass

import structlog
from docling.document_converter import DocumentConverter
from docling.datamodel.base_models import InputFormat
from docling.datamodel.pipeline_options import PdfPipelineOptions
from docling.document_converter import PdfFormatOption

logger = structlog.get_logger(__name__)


@dataclass
class ParsedChunk:
    content: str
    page_number: int
    section_heading: str
    chunk_type: str  # text, table, heading
    metadata: dict


class DocumentParser:
    """Layout-aware document parser using Docling."""

    def __init__(self):
        pipeline_options = PdfPipelineOptions()
        pipeline_options.do_ocr = True
        pipeline_options.do_table_structure = True

        self.converter = DocumentConverter(
            format_options={
                InputFormat.PDF: PdfFormatOption(pipeline_options=pipeline_options),
            }
        )

    async def parse(self, file_path: str) -> List[ParsedChunk]:
        """Parse a document and return structured chunks."""
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, self._parse_sync, file_path)

    def _parse_sync(self, file_path: str) -> List[ParsedChunk]:
        logger.info("Parsing document", path=file_path)
        chunks = []

        try:
            result = self.converter.convert(file_path)
            doc = result.document

            current_heading = "Introduction"
            current_page = 1

            for item, _ in doc.iterate_items():
                item_type = type(item).__name__.lower()

                # Track page numbers
                if hasattr(item, "prov") and item.prov:
                    for prov in item.prov:
                        if hasattr(prov, "page_no"):
                            current_page = prov.page_no

                # Track headings
                if "sectionheader" in item_type or "heading" in item_type:
                    current_heading = item.text if hasattr(item, "text") else str(item)
                    chunks.append(ParsedChunk(
                        content=current_heading,
                        page_number=current_page,
                        section_heading=current_heading,
                        chunk_type="heading",
                        metadata={},
                    ))

                # Text paragraphs
                elif "textitem" in item_type or "paragraph" in item_type:
                    text = item.text if hasattr(item, "text") else str(item)
                    if text and len(text.strip()) > 20:
                        chunks.append(ParsedChunk(
                            content=text.strip(),
                            page_number=current_page,
                            section_heading=current_heading,
                            chunk_type="text",
                            metadata={},
                        ))

                # Tables — keep intact
                elif "table" in item_type:
                    try:
                        table_text = item.export_to_markdown()
                        if table_text and len(table_text.strip()) > 10:
                            chunks.append(ParsedChunk(
                                content=table_text.strip(),
                                page_number=current_page,
                                section_heading=current_heading,
                                chunk_type="table",
                                metadata={"rows": getattr(item, "num_rows", 0)},
                            ))
                    except Exception:
                        pass

                # List items
                elif "listitem" in item_type:
                    text = item.text if hasattr(item, "text") else str(item)
                    if text and len(text.strip()) > 5:
                        chunks.append(ParsedChunk(
                            content=text.strip(),
                            page_number=current_page,
                            section_heading=current_heading,
                            chunk_type="list_item",
                            metadata={},
                        ))

        except Exception as e:
            logger.error("Docling parsing failed, falling back to text extraction", error=str(e))
            chunks = self._fallback_parse(file_path)

        # Merge small consecutive text chunks
        chunks = self._merge_small_chunks(chunks)
        logger.info("Document parsed", path=file_path, chunks=len(chunks))
        return chunks

    def _merge_small_chunks(self, chunks: List[ParsedChunk], min_size: int = 100) -> List[ParsedChunk]:
        """Merge consecutive small text chunks to avoid tiny embeddings."""
        if not chunks:
            return chunks

        merged = []
        buffer = None

        for chunk in chunks:
            if chunk.chunk_type in ("heading",):
                if buffer:
                    merged.append(buffer)
                    buffer = None
                merged.append(chunk)
                continue

            if buffer is None:
                buffer = chunk
            elif len(buffer.content) < min_size and chunk.chunk_type == buffer.chunk_type:
                buffer.content += " " + chunk.content
            else:
                merged.append(buffer)
                buffer = chunk

        if buffer:
            merged.append(buffer)

        return merged

    def _fallback_parse(self, file_path: str) -> List[ParsedChunk]:
        """Simple fallback text extraction if Docling fails."""
        ext = Path(file_path).suffix.lower()
        chunks = []

        try:
            if ext == ".txt":
                with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
                    text = f.read()
                paragraphs = [p.strip() for p in text.split("\n\n") if p.strip()]
                for i, para in enumerate(paragraphs):
                    chunks.append(ParsedChunk(
                        content=para,
                        page_number=1,
                        section_heading="Content",
                        chunk_type="text",
                        metadata={},
                    ))
            elif ext == ".pdf":
                import pypdf
                reader = pypdf.PdfReader(file_path)
                for i, page in enumerate(reader.pages):
                    text = page.extract_text()
                    if text and text.strip():
                        chunks.append(ParsedChunk(
                            content=text.strip(),
                            page_number=i + 1,
                            section_heading="Page Content",
                            chunk_type="text",
                            metadata={},
                        ))
        except Exception as e:
            logger.error("Fallback parsing failed", error=str(e))

        return chunks


_parser = None


def get_document_parser() -> DocumentParser:
    global _parser
    if _parser is None:
        _parser = DocumentParser()
    return _parser
