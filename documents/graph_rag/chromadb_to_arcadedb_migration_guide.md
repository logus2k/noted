# Migration Blueprint: Consolidating ChromaDB into ArcadeDB for Local GraphRAG

This document outlines the end-to-end migration strategy for consolidating a local ChromaDB vector store into an ArcadeDB multi-model database. Designed for a containerized environment utilizing a local LLM (Gemma 4), this migration aims to eliminate network latency, combine semantic search with deep relationship traversal, and dramatically improve frontend UI/UX responsiveness.

## Phase 1: Architecture & Container Strategy

Currently, the infrastructure relies on multiple discrete hops: `App -> ChromaDB -> App -> Graph/MLflow -> App`. Consolidation moves this into a single cohesive network.

### 1.1 Docker Network Optimization
To ensure the lowest possible latency between your Python application, Gemma 4, and ArcadeDB, they must share a dedicated user-defined Docker bridge network. This allows DNS resolution by container name and bypasses the default bridge overhead.

### 1.2 Resource Allocation (Memory Tuning)
Since Gemma 4 (especially MoE versions) requires significant RAM/VRAM, ArcadeDB must be tuned to avoid OS-level swapping.
* **Limit Heap Space:** Set ArcadeDB's JVM heap to a moderate level (e.g., 2GB-4GB using `-Xmx4g`). ArcadeDB relies more heavily on the OS Page Cache for its O(1) pointer hopping.
* **Prioritize Page Cache:** Leave enough free system RAM so the OS can cache ArcadeDB's bucket files. This is what guarantees sub-5ms traversals.

## Phase 2: Unified Schema Design in ArcadeDB

Before migrating data, you must define the schema. Unlike ChromaDB which only holds flat metadata, ArcadeDB requires Vertex (Node) and Edge (Relationship) types.

### 2.1 Defining the Graph Topology
Run the following Cypher/SQL script against the ArcadeDB console or via the initialization script to prepare the multi-model structure.

```cypher
/* Vertex Types */
CREATE VERTEX TYPE Document;
CREATE VERTEX TYPE Notebook;
CREATE VERTEX TYPE Run;
CREATE VERTEX TYPE Metric;

/* Edge Types for O(1) Traversal */
CREATE EDGE TYPE HAS_RUN;
CREATE EDGE TYPE LOGGED;
CREATE EDGE TYPE EXTRACTED_FROM;

/* Vector Index Configuration (Assuming 1536 dims, adjust to your embedder) */
ALTER TYPE Document ADD COLUMN embedding BINARY;
ALTER TYPE Notebook ADD COLUMN embedding BINARY;

CREATE INDEX ON Document (embedding) VECTOR HNSW ('distanceFunction', 'cosine');
CREATE INDEX ON Notebook (embedding) VECTOR HNSW ('distanceFunction', 'cosine');

/* Standard Indexes for fast entry points */
CREATE INDEX ON Run (run_id) UNIQUE;
CREATE INDEX ON Notebook (path) NOTUNIQUE;
```

> **Hint:** Do not index every single property. Only index properties that act as "Entry Points" for your queries (like `run_id` or `embedding`). Once the engine finds the entry node, it uses physical pointers (edges) to find the rest, requiring no further indexes.

---

## Phase 3: The Data Migration (ETL)

This phase involves extracting your existing embeddings from ChromaDB and mapping your local MLflow files into the ArcadeDB schema.

### 3.1 Exporting from ChromaDB
Write a temporary Python script to dump your Chroma collections. You want to extract the `id`, `document`, `embedding`, and `metadata`.

### 3.2 Batch Ingestion into ArcadeDB
Do not insert records one by one. Use ArcadeDB's batch transactional API or pure Cypher batching over the binary port (7687 for Bolt or HTTP batch). This is critical for speed.

```python
import arcadedb
# Using the official python client
client = arcadedb.Client("http://arcadedb:2480", "root", "password")

def migrate_batch(chroma_batch):
    # Construct a Cypher UNWIND query for massive insertion speed
    query = '''
    UNWIND $batch AS row
    MERGE (d:Document {doc_id: row.id})
    SET d.text = row.document,
        d.embedding = row.embedding,
        d.author = row.metadata.author
    '''
    client.query(query, parameters={"batch": chroma_batch})
```

### 3.3 Ingesting Local MLflow Data
Iterate through your local `./mlruns` directory. For each YAML file, construct a graph path: `Notebook -> HAS_RUN -> Run -> LOGGED -> Metric`. Use the same `UNWIND` Cypher strategy.

## Phase 4: Refactoring Python Skills (The Orchestrator)

This is where latency drops dramatically. Your LLM (Gemma 4) will no longer choose between a "Vector Tool" and a "Graph Tool". Instead, it will use a Unified Hybrid query.

### 4.1 The Hybrid Cypher Approach
Rewrite your retrieval function. The LLM simply provides the search query, your Python app calculates the embedding, and ArcadeDB handles the vector search AND the deep relationship drill-down in a single millisecond-level transaction.

```python
def unified_rag_search(user_query_text):
    # 1. Embed the query locally
    query_vector = local_embedding_model.encode(user_query_text)
    
    # 2. Single Hybrid Query to ArcadeDB
    cypher = '''
    // Step A: Vector Semantic Search
    MATCH (nb:Notebook)
    WHERE nb.embedding <=> $query_vector
    
    // Step B: Pointer-Hopping (Drill Down)
    OPTIONAL MATCH (nb)-[:HAS_RUN]->(r:Run)-[:LOGGED]->(m:Metric {name: 'MSE'})
    
    // Step C: Return structured context for Gemma 4
    RETURN nb.path as Notebook, 
           nb.text as Description, 
           r.run_id as Run, 
           min(m.value) as Best_MSE
    LIMIT 3
    '''
    
    results = client.query(cypher, parameters={"query_vector": query_vector})
    return format_for_gemma(results)
```

## Phase 5: UI/UX & Latency Improvements

By shifting the heavy lifting to the database engine, the UI can become vastly more responsive.

| Metric | Current State (Siloed) | Future State (Consolidated) |
| :--- | :--- | :--- |
| **Response Time** | Loader spins for ~2-3 seconds while Python orchestrates multiple DB calls. | Data context is retrieved in < 50ms. Loader time is strictly limited by Gemma 4's generation speed. |
| **Streaming** | UI waits for the full final answer to render. | Since retrieval is instant, LLM streaming can begin immediately, improving perceived latency. |
| **Follow-ups** | Follow-up questions require starting the search over. | **Contextual pre-fetching:** Return neighbors alongside the query so follow-up UI clicks are instantaneous. |

### 5.1 UI Tip: Exposing the Graph to the User
Since your backend now inherently understands relationships, your UI can reflect this. Instead of returning plain text, have your Python API return the text *plus* the connected edge data. The UI can then display interactive "pills" or a mini-graph.

*Example:* When Gemma 4 answers about "Notebook A", the UI can render clickable tags for "Run 442" and "Best MSE: 0.04" immediately below the chat bubble, because ArcadeDB retrieved them for free during the initial vector search.
