"""Word Factory (V0.1) — خط لوله Word → JSON ساختاریافته.

اجزای عمومی:
    from factory import DocumentProcessingService, NormalizationPolicy

خط لوله: intake → validate → parse → structure → metadata →
          normalize → quality → export (5 خروجی)
محدودیت V0.1: بدون LLM/ENRICHED، بدون ES، بدون queue/worker، بدون DB.
"""
from .errors import (FactoryError, FormatDetectionError,
                     IntakeError, ParseError, QualityCheckFailed,
                     UnsupportedFormatError, ValidationFailedError)
from .corpus import (CORPUS_VERSION, CorpusError, build_corpus)
from .dump import (DUMP_VERSION, DumpError, dump_summary, generate_dump,
                   validate_dump)
from .export import JsonlExporter, ProcessingManifest
from .intake import DocumentIntakeService, detect_format, sha256_file
from .metadata import MetadataExtractor
from .models import (Block, DocumentMetadata, FileRecord,
                     FACTORY_VERSION, MANIFEST_VERSION, NORM_VERSION,
                     PARSER_VERSION, ProcessedDocument, QualityReport,
                     StructureTree, content_hash, short_id)
from .normalize import (NormalizationPolicy, PersianNormalizer,
                        verify_no_semantic_change)
from .parser import (DocParserAdapter, DocxParser, DocumentParser,
                     ParseOutcome, make_parser)
from .quality import QualityValidator
from .service import DocumentProcessingService
from .structure import extract_structure
from .validator import FileValidator, ValidationOutcome

__all__ = [
    "DocumentProcessingService", "DocumentIntakeService", "detect_format",
    "sha256_file", "FileValidator", "ValidationOutcome",
    "DUMP_VERSION", "DumpError", "generate_dump", "validate_dump",
    "dump_summary",
    "CORPUS_VERSION", "CorpusError", "build_corpus",
    "DocumentParser", "DocxParser", "DocParserAdapter", "ParseOutcome",
    "make_parser", "extract_structure", "MetadataExtractor",
    "PersianNormalizer", "NormalizationPolicy", "verify_no_semantic_change",
    "QualityValidator", "JsonlExporter", "ProcessingManifest",
    "Block", "DocumentMetadata", "FileRecord", "ProcessedDocument",
    "QualityReport", "StructureTree", "content_hash", "short_id",
    "FactoryError", "IntakeError", "FormatDetectionError",
    "UnsupportedFormatError", "ValidationFailedError", "ParseError",
    "QualityCheckFailed",
    "PARSER_VERSION", "NORM_VERSION", "MANIFEST_VERSION", "FACTORY_VERSION",
]

__version__ = "0.1.0"
