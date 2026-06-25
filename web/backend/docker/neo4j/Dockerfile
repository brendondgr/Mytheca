# Velora's custom Neo4j image — the Story Graph substrate.
#
# Built and started automatically by `python app.py` (see ensure_docker_services
# in app.py and web/backend/docker-compose.yml). You never build this by hand.
#
# Why a custom image rather than the stock `neo4j` image:
#   * pinned to 5.26 community — the first release where node labels and
#     relationship types can be referenced *dynamically* from a bound parameter
#     (CREATE (n:$($type) {...})), which is exactly what lets user-defined graph
#     types travel the indexed label path safely (see plan §6.2);
#   * APOC Core enabled out of the box (bundled in the image's /var/lib/neo4j/labs;
#     NEO4J_PLUGINS copies it in at startup — no network fetch);
#   * dev-friendly defaults (modest heap/pagecache, APOC file procs) baked in so
#     the compose file and .env stay about ports/credentials only.
FROM neo4j:5.26-community

# Enable APOC Core (moved from the bundled labs dir into plugins at container start).
ENV NEO4J_PLUGINS='["apoc"]'

# APOC procedure allowlist + file import/export (used by future export/lore tooling).
ENV NEO4J_apoc_export_file_enabled=true \
    NEO4J_apoc_import_file_enabled=true \
    NEO4J_dbms_security_procedures_unrestricted=apoc.* \
    NEO4J_dbms_security_procedures_allowlist=apoc.*

# Modest memory for a local dev box (override in prod via compose/env).
ENV NEO4J_server_memory_heap_initial__size=512m \
    NEO4J_server_memory_heap_max__size=1g \
    NEO4J_server_memory_pagecache_size=512m

# Listen on all interfaces inside the container so the published host ports work.
ENV NEO4J_server_default__listen__address=0.0.0.0

EXPOSE 7474 7687
