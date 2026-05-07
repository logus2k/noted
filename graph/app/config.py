"""Knowledge Graph service configuration from environment variables."""

import os

MLFLOW_TRACKING_URI = os.environ.get('MLFLOW_TRACKING_URI', 'http://mlflow:5000')
AIRFLOW_API_URL = os.environ.get('AIRFLOW_API_URL', 'http://noted-airflow-apiserver:8080')
AIRFLOW_BASE_PATH = os.environ.get('AIRFLOW_BASE_PATH', '/airflow')
AIRFLOW_USERNAME = os.environ.get('AIRFLOW_USERNAME', 'airflow')
AIRFLOW_PASSWORD = os.environ.get('AIRFLOW_PASSWORD', 'airflow')

# noted backend for file system access (projects, mounts, DVC, Hydra)
NOTED_API_URL = os.environ.get('NOTED_API_URL', 'http://noted:8123')

# Paths accessible inside the container (via volume mounts)
PROJECTS_DIR = os.environ.get('PROJECTS_DIR', '/app/data/projects')
MOUNTS_DIR = os.environ.get('MOUNTS_DIR', '/app/mounts')

HOST = os.environ.get('GRAPH_HOST', '0.0.0.0')
PORT = int(os.environ.get('GRAPH_PORT', '5523'))

CACHE_TTL_SECONDS = int(os.environ.get('GRAPH_CACHE_TTL', '300'))

# ArcadeDB (GraphRAG persistence)
ARCADEDB_URL = os.environ.get('ARCADEDB_URL', 'http://noted-arcadedb:2480')
ARCADEDB_DATABASE = os.environ.get('ARCADEDB_DATABASE', 'noted')
ARCADEDB_USER = os.environ.get('ARCADEDB_USER', 'root')
ARCADEDB_PASSWORD = os.environ.get('ARCADEDB_PASSWORD', 'noted-dev')
ARCADEDB_TIMEOUT = int(os.environ.get('ARCADEDB_TIMEOUT', '120'))
ARCADEDB_SYNC_ENABLED = os.environ.get('ARCADEDB_SYNC_ENABLED', 'true').lower() == 'true'

# Gemma via agent_server (entity extraction, community summaries, synthesis).
# Use the dedicated `noted_graph` agent_server preset - it ships the system
# prompt that establishes the GraphRAG analyst persona + output discipline.
# Per-task instructions live in user prompts.
LLM_BASE_URL = os.environ.get('LLM_BASE_URL', 'http://agent_server:7701')
LLM_MODEL_ID = os.environ.get('LLM_MODEL_ID', 'noted_graph')
LLM_TIMEOUT = int(os.environ.get('LLM_TIMEOUT', '120'))

# noted-rag sidecar (embedding endpoint for sameAs + community routing)
RAG_BASE_URL = os.environ.get('RAG_BASE_URL', 'http://noted-rag:8200')

# GraphRAG retrieval + extraction parameters (resolved Q A-F)
# Q C: extraction chunk size (heading-aware level >=3)
EXTRACT_CHUNK_TARGET_TOKENS = int(os.environ.get('EXTRACT_CHUNK_TARGET_TOKENS', '600'))
EXTRACT_CHUNK_MIN_TOKENS = int(os.environ.get('EXTRACT_CHUNK_MIN_TOKENS', '200'))
EXTRACT_CHUNK_MAX_TOKENS = int(os.environ.get('EXTRACT_CHUNK_MAX_TOKENS', '800'))
# Q D: extraction confidence floor
ENTITY_CONFIDENCE_FLOOR = float(os.environ.get('ENTITY_CONFIDENCE_FLOOR', '0.6'))
# Concurrent chunk-extraction workers. Should match (or slightly exceed)
# the llama-server slot count for gemma-4 (currently 4). Raising past the
# slot count just queues at the server side; lower than that wastes slots.
ENTITY_EXTRACT_PARALLELISM = int(os.environ.get('ENTITY_EXTRACT_PARALLELISM', '4'))
# Concurrent community-summary workers. Same llama-server slot constraint
# as entity extraction — raising past the slot count just queues server-
# side. Defaults to ENTITY_EXTRACT_PARALLELISM so both LLM-bound phases
# share one knob in practice.
COMMUNITY_SUMMARY_PARALLELISM = int(
    os.environ.get('COMMUNITY_SUMMARY_PARALLELISM', str(ENTITY_EXTRACT_PARALLELISM))
)

# Picture + table description pass during ingest. When ON, every Docling
# `PictureItem` / `TableItem` in a converted PDF/DOCX/PPTX/HTML gets a
# short caption from the corresponding agent_server preset
# (`picture_describer` / `table_describer`). Captions are folded into
# the chunk stream just before extraction so they flow through embed +
# entity extraction identically to native text. Default OFF until
# validated on a real corpus; flip to true via env once the new
# ingest path lands and is tested.
ENABLE_DOC_DESCRIPTIONS = os.environ.get('ENABLE_DOC_DESCRIPTIONS', 'false').lower() == 'true'
# Concurrent description workers. Same llama-server slot constraint as
# entity extraction — raising past the gemma-4 slot count just queues
# server-side. Defaults to ENTITY_EXTRACT_PARALLELISM so all GPU-bound
# ingest phases share one knob in practice.
DOC_DESCRIPTION_PARALLELISM = int(
    os.environ.get('DOC_DESCRIPTION_PARALLELISM', str(ENTITY_EXTRACT_PARALLELISM))
)
# Skip pictures smaller than this many pixels (width × height). Filters
# decorative bullet glyphs, separator marks, and tiny inline icons that
# would just waste a vision call.
PICTURE_DESCRIPTION_MIN_AREA_PX = int(
    os.environ.get('PICTURE_DESCRIPTION_MIN_AREA_PX', '10000')
)

# Feature flag: route per-doc graph writes (`add_doc_merge`) through the
# GraphBatch HTTP endpoint (`POST /api/v1/batch/<db>?lightEdges=false`)
# introduced in ArcadeDB v26.3.2. The legacy UNWIND+MATCH+CREATE path
# stays in place and is the default until this flag is flipped on.
# See documents/kb/kb_import_export.md Phase 2 for the design.
USE_GRAPHBATCH_V2 = os.environ.get('USE_GRAPHBATCH_V2', 'false').lower() == 'true'
# Q B: Leiden target community size
COMMUNITY_TARGET_SIZE = int(os.environ.get('COMMUNITY_TARGET_SIZE', '50'))
# Retrieval tuning (see graph_rag_notes.md §5.3)
GLOBAL_TOP_COMMUNITIES = int(os.environ.get('GLOBAL_TOP_COMMUNITIES', '3'))
TOP_ENTITIES_N = int(os.environ.get('TOP_ENTITIES_N', '10'))
LOCAL_TRAVERSAL_HOPS = int(os.environ.get('LOCAL_TRAVERSAL_HOPS', '3'))
SUBGRAPH_CAP = int(os.environ.get('SUBGRAPH_CAP', '50'))
SAMEAS_EXPAND_CONFIDENCE = float(os.environ.get('SAMEAS_EXPAND_CONFIDENCE', '0.85'))

# Domain layout. Each Domain is fully self-contained on disk:
#   data/domains/<domain_id>/manifest.json
#   data/domains/<domain_id>/sources/      user content
#   data/domains/<domain_id>/state/        per-Domain persistent markers
#   data/domains/<domain_id>/skills/       per-Domain skills (folder-per-skill)
#   data/domains/<domain_id>/tools/        per-Domain tool definitions
#
# No cross-Domain sharing of source files - if the same file is wanted in
# two Domains, it's uploaded twice (one copy lives in each Domain's
# sources/). Trades a bit of disk duplication for full Domain isolation.
DOMAIN_HOME_DIR = os.environ.get('DOMAIN_HOME_DIR', '/app/data/domains')

# The pinned, always-active Domain that holds universal Assistant behavior
# (fairness, honesty, voice, citation conventions, multi-domain awareness)
# plus general-purpose tools (create_file, etc.). Cannot be deactivated.
GENERAL_DOMAIN_ID = os.environ.get('GENERAL_DOMAIN_ID', 'general')

# Legacy paths used ONLY by app.migration to detect pre-Domain layouts.
# Code outside migration.py must not reference these directly.
_LEGACY_KB_HOME_DIR = '/app/data/kb'
_LEGACY_KB_SOURCES_DIR = '/app/data/kb_sources'
_LEGACY_GRAPH_STATE_DIR = '/app/data/graph_state'
_LEGACY_GLOBAL_PROJECT_ID = '__global__'
_LEGACY_NOTED_CORPUS_COLLECTION = 'noted_corpus'
_LEGACY_NOTED_ENTITIES_COLLECTION = 'gr_entities'
_LEGACY_NOTED_SUMMARIES_COLLECTION = 'gr_summaries'

# Back-compat shims for storage/scanners/retriever that still reference
# the old constants as fallback defaults. New code should resolve these
# via DomainContext + corpus.sources_dir(domain_id) instead. Once those
# call sites are updated (Phase A10 follow-up), these shims can be dropped.
GLOBAL_PROJECT_ID = 'noted'
DEFAULT_KB_ID = 'noted'
KB_SOURCES_DIR = os.path.join(DOMAIN_HOME_DIR, 'noted', 'sources')

# Docling (PDF / DOCX / PPTX / HTML ingestion via app.scanners.pdf_scanner).
# Cache dir set by DOCLING_CACHE_DIR (compose); models live alongside
# bge-m3 at /data/models/docling/. Total footprint ~1.15 GB.
DOCLING_GPU_ENABLED = os.environ.get('DOCLING_GPU_ENABLED', 'auto')   # auto | true | false
DOCLING_TABLE_MODE = os.environ.get('DOCLING_TABLE_MODE', 'accurate')  # accurate | fast
DOCLING_MAX_PAGES = int(os.environ.get('DOCLING_MAX_PAGES', '2000'))   # safety cap; 0 = no cap
DOCLING_OCR = os.environ.get('DOCLING_OCR', 'false').lower() == 'true'  # opt-in for scanned PDFs
