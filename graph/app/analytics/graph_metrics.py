"""PageRank + Leiden clustering over the global entity graph.

Both algorithms run post-extraction and post-sameAs. Results are attached
to entity nodes as:
  rank         (float) - PageRank score
  community_id (int)   - Leiden cluster membership

Only entities in the global thematic layer are ranked/clustered; structured
scanner entities (run, data_file, etc.) are not part of the GraphRAG
retrieval surface yet.
"""

from __future__ import annotations

import logging
import time
from typing import Iterable

import igraph as ig
import leidenalg
import networkx as nx

from app.config import COMMUNITY_TARGET_SIZE
from app.models import Entity, Relationship

logger = logging.getLogger(__name__)


# Relationship types that participate in the analytics subgraph (provide
# the connectivity signal for community formation).
_ANALYTICS_EDGE_TYPES = {
    'mentions',       # chunk -> entity (the bridge that connects co-mentioned entities)
    'chunked_into',   # doc -> chunk
    'defines', 'documents',
    'similar_to',     # entity <-> entity (cosine-based topical relatedness)
    'sameAs',         # entity <-> entity (true identity)
}

# Edge weights tuning the partition. Higher = stronger pull toward
# clustering. sameAs (true identity) should be the strongest. Mentions
# and chunked_into are the structural backbone; weighted modestly so
# they bridge but don't dominate.
_EDGE_WEIGHT_SAMEAS = 2.0
_EDGE_WEIGHT_SIMILAR = {'high': 1.0, 'medium': 0.5, 'low': 0.2}
_EDGE_WEIGHT_MENTIONS = 0.5
_EDGE_WEIGHT_CHUNKED_INTO = 0.5
_EDGE_WEIGHT_DEFAULT = 0.5


def compute_pagerank_and_communities(
    entities: list[Entity],
    relationships: list[Relationship],
    bridge_entities: list[Entity] | None = None,
) -> tuple[dict[str, float], dict[str, int]]:
    """Run PageRank + Leiden over the analytics subgraph.

    `entities` are the nodes that get COMMUNITY MEMBERSHIP (thematic
    entities only). `bridge_entities` are extra nodes included in the
    Leiden graph to provide CONNECTIVITY (typically markdown_chunk +
    markdown_doc) - they participate in clustering but the returned
    communities dict only includes the original `entities`.

    Returns:
      ranks: {entity_id: rank_score} - PageRank for both entities and bridges.
      communities: {entity_id: community_id} - membership for `entities` only.
    """
    nxg = nx.Graph()
    entity_id_set = {e.id for e in entities}
    bridge_id_set = {e.id for e in (bridge_entities or [])}
    all_ids = entity_id_set | bridge_id_set

    for e in entities:
        nxg.add_node(e.id, type=e.type, _is_bridge=False)
    for e in (bridge_entities or []):
        nxg.add_node(e.id, type=e.type, _is_bridge=True)

    for r in relationships:
        if r.type not in _ANALYTICS_EDGE_TYPES:
            continue
        if r.source not in all_ids or r.target not in all_ids:
            continue
        # Choose weight per edge type
        if r.type == 'sameAs':
            weight = _EDGE_WEIGHT_SAMEAS
        elif r.type == 'similar_to':
            band = (r.properties or {}).get('confidence', 'low')
            weight = _EDGE_WEIGHT_SIMILAR.get(band, 0.2)
        elif r.type == 'mentions':
            weight = _EDGE_WEIGHT_MENTIONS
        elif r.type == 'chunked_into':
            weight = _EDGE_WEIGHT_CHUNKED_INTO
        else:
            weight = _EDGE_WEIGHT_DEFAULT
        # Accumulate weight for parallel edges between the same pair
        if nxg.has_edge(r.source, r.target):
            nxg[r.source][r.target]['weight'] = nxg[r.source][r.target].get('weight', 1.0) + weight
        else:
            nxg.add_edge(r.source, r.target, weight=weight)

    if nxg.number_of_nodes() == 0:
        logger.info('Analytics subgraph empty; skipping PageRank + Leiden.')
        return {}, {}

    # PageRank over the weighted undirected graph.
    try:
        ranks = nx.pagerank(nxg, weight='weight')
    except Exception as e:
        logger.warning('PageRank failed (%s). Falling back to degree.', e)
        ranks = {n: float(nxg.degree(n)) for n in nxg.nodes}

    # Leiden via leidenalg. Convert networkx -> igraph.
    nodes = list(nxg.nodes)
    node_index = {n: i for i, n in enumerate(nodes)}
    edges = []
    weights = []
    for u, v, d in nxg.edges(data=True):
        edges.append((node_index[u], node_index[v]))
        weights.append(d.get('weight', 1.0))

    ig_graph = ig.Graph(n=len(nodes), edges=edges, directed=False)
    ig_graph.es['weight'] = weights

    # RBConfigurationVertexPartition has a tunable resolution_parameter that
    # directly controls community granularity (lower -> fewer, larger
    # communities). The first full rebuild on ModularityVertexPartition
    # (default resolution=1.0) fragmented ~5000 entities into 1358 mostly-
    # singleton communities; resolution=0.5 is the conservative starting
    # point per Q14 of open_questions.md. Tune toward COMMUNITY_TARGET_SIZE
    # after observing the new pattern.
    try:
        partition = leidenalg.find_partition(
            ig_graph,
            leidenalg.RBConfigurationVertexPartition,
            weights='weight',
            resolution_parameter=0.5,
            n_iterations=10,
            seed=42,
        )
    except Exception as e:
        logger.warning('Leiden failed (%s). Assigning all to community 0.', e)
        communities = {n: 0 for n in nodes if n in entity_id_set}
        return ranks, communities

    # Build full community map from Leiden output
    full_communities: dict[str, int] = {}
    for cid, nodelist in enumerate(partition):
        for idx in nodelist:
            full_communities[nodes[idx]] = cid

    # Return community membership ONLY for the thematic entities; chunks
    # and docs were included as bridge nodes for connectivity, not as
    # first-class community members. Their communities are dropped here.
    communities: dict[str, int] = {
        nid: cid for nid, cid in full_communities.items() if nid in entity_id_set
    }

    # Renumber communities to skip empty ones (after filtering bridges out,
    # some communities may have only bridge members and disappear).
    used = sorted(set(communities.values()))
    remap = {old: new for new, old in enumerate(used)}
    communities = {nid: remap[cid] for nid, cid in communities.items()}

    sizes = _community_sizes(communities)
    bridge_count = sum(1 for n in nodes if nxg.nodes[n].get('_is_bridge'))
    logger.info(
        'PageRank + Leiden: %d nodes (%d entities + %d bridges), %d edges; '
        '%d communities for entities; size hist %s',
        nxg.number_of_nodes(), nxg.number_of_nodes() - bridge_count, bridge_count,
        nxg.number_of_edges(), len(sizes), sizes,
    )
    return ranks, communities


def _community_sizes(communities: dict[str, int]) -> dict[int, int]:
    out: dict[int, int] = {}
    for cid in communities.values():
        out[cid] = out.get(cid, 0) + 1
    return out


def compute_pagerank_and_communities_arcadedb(
    entities: list[Entity],
    sameas_rels: list[Relationship],
    similar_rels: list[Relationship],
    arcadedb_client,
    project_id: str,
) -> tuple[dict[str, float], dict[str, int]]:
    """Server-side PageRank + Louvain via ArcadeDB's algo.* Cypher procedures.

    Default analytics backend when GRAPH_ANALYTICS_BACKEND=arcadedb (Phase 4
    of the 2026-05-13 scalability refactor).

    Edge-weight scheme (materialized into `r.weight` before the algos run):
      - sameAs                  -> 2.0   (strongest pull — true identity)
      - similar_to high band    -> 1.0
      - similar_to medium band  -> 0.5
      - similar_to low band     -> 0.2
      - mentions / chunked_into / defines / documents / default -> 0.5
      - member_of / summarizes  -> 0.0   (structural; shouldn't pull clusters)

    Picks `algo.louvain` (not `algo.leiden`) because Louvain accepts a
    `weightProperty` parameter in ArcadeDB. Unweighted Leiden produces
    over-fragmented communities (130 singletons + 3 mega-clusters seen
    on ai_and_jobs at resolution=0.5); weighted Louvain matches the
    Python path's RBConfiguration weighted partition more closely.

    Pre-condition: caller must have written sameAs + similar_to edges
    to the graph BEFORE invoking this; otherwise the algos see stale
    state. (The normal recluster flow writes them in
    replace_analytics_layer AFTER this function returns, so the FIRST
    recluster after this code lands will see the PRIOR recluster's
    edges — converges on subsequent reclusters.)

    Returns:
      ranks: {entity_id: rank_score} for thematic entities only.
      communities: {entity_id: community_id} for thematic entities only.
    """
    thematic_ids = {e.id for e in entities}
    if not thematic_ids:
        logger.info('arcadedb analytics: no thematic entities; returning empty.')
        return {}, {}

    logger.info(
        'arcadedb analytics: running weighted CALL algo.pagerank + CALL algo.louvain '
        'against the persisted graph (project=%s, thematic_entities=%d)',
        project_id, len(thematic_ids),
    )

    # Pre-step: materialize r.weight per RELATES edge type. Four passes
    # for clarity; each is a single bulk SET keyed by edge type +
    # (for similar_to) confidence band found in properties_json.
    # Cost: linear in edge count, but a single transaction per pass.
    _t0 = time.perf_counter()
    pid = project_id
    # Pass 1 — base: 0.5 for everything in the project. Covers mentions,
    # chunked_into, defines, documents, and any other unenumerated type.
    arcadedb_client.command(
        '''MATCH (a:Entity)-[r:RELATES]->(b:Entity)
           WHERE $pid IN a.project_ids AND $pid IN b.project_ids
           SET r.weight = 0.5''',
        {'pid': pid},
    )
    # Pass 2 — sameAs: 2.0 (strongest pull).
    arcadedb_client.command(
        '''MATCH (a:Entity)-[r:RELATES]->(b:Entity)
           WHERE $pid IN a.project_ids AND $pid IN b.project_ids
             AND r.type = "sameAs"
           SET r.weight = 2.0''',
        {'pid': pid},
    )
    # Pass 3 — similar_to bands. Confidence band is stored inside
    # properties_json (a serialized JSON blob). Match via CONTAINS on
    # the exact Python json.dumps formatting ('"confidence": "<band>"'
    # — note the space after the colon; verified live 2026-05-13).
    for band, weight in (('high', 1.0), ('medium', 0.5), ('low', 0.2)):
        arcadedb_client.command(
            '''MATCH (a:Entity)-[r:RELATES]->(b:Entity)
               WHERE $pid IN a.project_ids AND $pid IN b.project_ids
                 AND r.type = "similar_to"
                 AND r.properties_json CONTAINS $needle
               SET r.weight = $w''',
            {'pid': pid, 'needle': f'"confidence": "{band}"', 'w': weight},
        )
    # Pass 4 — structural edges shouldn't pull clusters.
    arcadedb_client.command(
        '''MATCH (a:Entity)-[r:RELATES]->(b:Entity)
           WHERE $pid IN a.project_ids AND $pid IN b.project_ids
             AND r.type IN ["member_of", "summarizes"]
           SET r.weight = 0.0''',
        {'pid': pid},
    )
    logger.info('arcadedb analytics: edge weights materialized (%.2fs)',
                time.perf_counter() - _t0)

    # algo.pagerank with weightProperty so high-weight edges (sameAs)
    # contribute more transition probability than low-weight ones.
    pagerank_rows = arcadedb_client.query(
        '''CALL algo.pagerank({dampingFactor: 0.85, maxIterations: 30, tolerance: 0.0001, weightProperty: "weight"})
           YIELD node, score
           RETURN node.id AS entity_id, score''',
        {},
    ) or []
    ranks: dict[str, float] = {}
    for row in pagerank_rows:
        eid = row.get('entity_id')
        if eid is not None:
            ranks[eid] = float(row.get('score') or 0.0)
    logger.info('arcadedb analytics: weighted PageRank returned %d node scores', len(ranks))

    # algo.louvain (not leiden — louvain accepts weightProperty). Default
    # max-iterations and tolerance are reasonable; weight-property is the
    # whole point of this pass.
    louvain_rows = arcadedb_client.query(
        '''CALL algo.louvain({maxIterations: 30, tolerance: 0.0001, weightProperty: "weight"})
           YIELD node, communityId, modularity
           RETURN node.id AS entity_id, communityId, modularity''',
        {},
    ) or []
    full_communities: dict[str, int] = {}
    final_modularity: float | None = None
    for row in louvain_rows:
        eid = row.get('entity_id')
        cid = row.get('communityId')
        if eid is not None and cid is not None:
            full_communities[eid] = int(cid)
        if row.get('modularity') is not None and final_modularity is None:
            final_modularity = float(row['modularity'])
    logger.info(
        'arcadedb analytics: weighted Louvain returned %d node assignments (modularity=%s)',
        len(full_communities),
        f'{final_modularity:.4f}' if final_modularity is not None else 'n/a',
    )

    # Filter communities to thematic entities only (drop bridge nodes —
    # chunks + docs participated in the partition but aren't first-class
    # community members in our model).
    communities: dict[str, int] = {
        eid: cid for eid, cid in full_communities.items() if eid in thematic_ids
    }

    # Renumber communities to be 0-indexed and contiguous (after bridge
    # filtering, some Leiden communities may have only bridge members
    # and disappear from the thematic-only view).
    used = sorted(set(communities.values()))
    remap = {old: new for new, old in enumerate(used)}
    communities = {eid: remap[cid] for eid, cid in communities.items()}

    sizes = _community_sizes(communities)
    logger.info(
        'arcadedb analytics: %d thematic entities -> %d communities; size hist %s',
        len(communities), len(sizes), sizes,
    )
    return ranks, communities


def apply_metrics_to_entities(
    entities: list[Entity],
    ranks: dict[str, float],
    communities: dict[str, int],
) -> None:
    """Mutate entities in place, adding rank + community_id properties."""
    for e in entities:
        if e.id in ranks:
            e.properties['rank'] = ranks[e.id]
        if e.id in communities:
            e.properties['community_id'] = communities[e.id]


def build_community_entities(
    communities: dict[str, int],
    entity_by_id: dict[str, Entity],
) -> tuple[list[Entity], list[Relationship]]:
    """Materialize one :Entity node per community + member_of edges.

    Community summaries are added by the community summarizer (a separate
    pass that calls Gemma).
    """
    by_cid: dict[int, list[str]] = {}
    for eid, cid in communities.items():
        by_cid.setdefault(cid, []).append(eid)

    community_entities: list[Entity] = []
    rels: list[Relationship] = []
    for cid, member_ids in by_cid.items():
        if not member_ids:
            continue
        # Dominant types in the community
        type_count: dict[str, int] = {}
        for mid in member_ids:
            t = entity_by_id.get(mid).type if entity_by_id.get(mid) else 'unknown'
            type_count[t] = type_count.get(t, 0) + 1
        dominant = sorted(type_count.items(), key=lambda kv: -kv[1])[:3]
        community_id = f'community:{cid}'
        community_entities.append(Entity(
            id=community_id,
            type='community',
            label=f'Community {cid}',
            properties={
                'community_id': cid,
                'level': 0,
                'member_count': len(member_ids),
                'dominant_entity_types': [{'type': t, 'count': c} for t, c in dominant],
            },
        ))
        for mid in member_ids:
            rels.append(Relationship(
                source=mid,
                target=community_id,
                type='member_of',
            ))
    return community_entities, rels
