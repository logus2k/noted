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
