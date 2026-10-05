# Retrieval lanes under forced RLS (EXPLAIN ANALYZE)

- dev queries: 44 · git dca59f5

| lane / role | n | exec p50 ms | exec p95 ms | GIN used | HNSW used | rows scanned p50 | max | indexes |
|---|---|---|---|---|---|---|---|---|
| dense/rls | 44 | 1.583 | 2.277 | 0/44 | 0/44 | 4560 | 4560 | child_chunks_pkey, child_chunks_ws_version, chunk_embeddings_pkey, parent_chunks_pkey, source_versions_pkey, sources_workspace_id_id_key |
| dense/no_rls | 44 | 1.435 | 1.675 | 0/44 | 0/44 | 6690 | 6690 | child_chunks_pkey, child_chunks_ws_version, chunk_embeddings_pkey, parent_chunks_pkey, source_versions_pkey |
| lexical/rls | 44 | 11.587 | 20.8 | 0/44 | 0/44 | 2330 | 2330 | child_chunks_pkey, child_chunks_ws_version, parent_chunks_pkey, source_versions_pkey, sources_pkey |
| lexical/no_rls | 44 | 11.165 | 19.597 | 44/44 | 0/44 | 1299 | 2183 | child_chunks_pkey, child_chunks_tsv, child_chunks_ws_version, parent_chunks_pkey, source_versions_pkey, sources_pkey |
