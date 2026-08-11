"""Phase 15 opening contracts: graph quality and Obsidian projection."""

from __future__ import annotations

import networkx as nx
import pytest

from vaultledger.config import REPO_ROOT, load_config
from vaultledger.evals.matrix import _answer_top_n
from vaultledger.evals.run import build_parser as build_eval_parser
from vaultledger.graph.ground_truth import load_ground_truth
from vaultledger.graph.index import _display_path, documents_from_chunks
from vaultledger.graph.lightrag_io import load_lightrag_graphml
from vaultledger.graph.model import GraphEntity, GraphRelation, GraphSnapshot
from vaultledger.graph.obsidian import export_obsidian_vault
from vaultledger.graph.ollama_binding import _chat_payload
from vaultledger.graph.quality import (
    account_alias_patterns,
    account_alias_table,
    canonical_name,
    score_graph,
    score_graph_with_account_aliases,
)
from vaultledger.retrieve.graph import LightRAGRetriever
from vaultledger.schemas import Chunk


def _ground_truth() -> GraphSnapshot:
    return load_ground_truth(REPO_ROOT / "data" / "ground_truth" / "entities.json")


def _doc_ids() -> list[str]:
    root = REPO_ROOT / "data" / "ground_truth"
    return sorted(path.stem for path in root.glob("*.json") if path.name != "entities.json")


def test_graph_config_pins_local_extractor_and_acceptance_threshold():
    cfg = load_config()
    assert cfg.graph.engine == "lightrag"
    assert cfg.graph.extraction_model == "ollama/qwen3:8b"
    assert cfg.graph.embedding_dim == 768
    assert cfg.graph.query_mode_default == "global"
    assert cfg.graph.answer_top_n == 12
    assert cfg.graph.entity_recall_min == 0.80


def test_ground_truth_denominator_is_explicit_and_relations_keep_evidence():
    graph = _ground_truth()
    kinds = {entity.kind for entity in graph.entities}
    assert len(graph.entities) == 15
    assert {"person", "employer", "client", "merchant", "account"} <= kinds
    assert len(graph.relations) == 15
    assert sum(len(relation.evidence_doc_ids) for relation in graph.relations) == 89
    assert not any("Nimbus address on" == entity.name for entity in graph.entities)
    accounts = {
        entity.name: entity.account_last4
        for entity in graph.entities
        if entity.kind == "account"
    }
    assert accounts == {
        "checking ****3390": "3390",
        "checking ****4021": "4021",
        "checking ****5567": "5567",
        "savings ****7788": "7788",
    }


def test_entity_metrics_deduplicate_and_only_normalize_representation():
    expected = GraphSnapshot(
        source="expected",
        entities=(GraphEntity("Priya Raman"), GraphEntity("Cedar Grove Media")),
        relations=(GraphRelation("Priya Raman", "invoiced", "Cedar Grove Media"),),
    )
    extracted = GraphSnapshot(
        source="extracted",
        entities=(
            GraphEntity('"PRIYA_RAMAN"'),
            GraphEntity("priya raman"),
            GraphEntity("Unrelated LLC"),
        ),
        relations=(GraphRelation("PRIYA RAMAN", "INVOICED", "cedar_grove_media"),),
    )
    quality = score_graph(extracted, expected)
    assert canonical_name(' "PRIYA_RAMAN" ') == "priya raman"
    assert quality.expected_entities == 2
    assert quality.extracted_entities == 2
    assert quality.matched_entities == 1
    assert quality.entity_recall == 0.5
    assert quality.entity_precision == 0.5
    assert quality.relation_recall == 1.0


def test_account_alias_rule_is_schema_derived_and_digit_anchored():
    expected = GraphSnapshot(
        source="expected",
        entities=(GraphEntity("checking ****4021", kind="account", account_last4="4021"),),
        relations=(),
    )
    assert account_alias_patterns("4021") == (
        r"\*{2,}\s*4021\b",
        r"ending\s+in\s+4021\b",
    )
    assert account_alias_table(expected) == {
        "checking ****4021": (r"\*{2,}\s*4021\b", r"ending\s+in\s+4021\b")
    }
    extracted = GraphSnapshot(
        source="extracted",
        entities=(
            GraphEntity("Account no. ****4021"),
            GraphEntity("Checking Account Ending in 4021"),
            GraphEntity("Account no. ****40210"),
            GraphEntity("Checking Account Ending in 14021"),
        ),
        relations=(),
    )
    quality = score_graph_with_account_aliases(extracted, expected)
    assert quality.alias_credited_nodes == 2
    assert quality.duplicate_alias_nodes == 1
    assert quality.quality.entity_recall == 1.0


def test_account_alias_precision_credits_one_entity_and_penalizes_duplicate_nodes():
    expected = GraphSnapshot(
        source="expected",
        entities=(
            GraphEntity("Priya Raman", kind="person"),
            GraphEntity("checking ****3390", kind="account", account_last4="3390"),
        ),
        relations=(),
    )
    extracted = GraphSnapshot(
        source="extracted",
        entities=(
            GraphEntity("Priya Raman"),
            GraphEntity("Account no. ****3390"),
            GraphEntity("Account: ****3390"),
            GraphEntity("Checking Account Ending in 3390"),
            GraphEntity("Noise"),
        ),
        relations=(),
    )
    quality = score_graph_with_account_aliases(extracted, expected)
    assert quality.quality.matched_entities == 2
    assert quality.quality.entity_recall == 1.0
    assert quality.quality.entity_precision == 2 / 5
    assert quality.alias_matched_expected == 1
    assert quality.alias_credited_nodes == 3
    assert quality.duplicate_alias_nodes == 2
    assert quality.node_counted_matched_entities == 4
    assert quality.node_counted_entity_precision == 4 / 5
    assert quality.precision_convention == "distinct_expected_one_credit_per_account"


def test_account_alias_rule_does_not_loosen_non_account_matching():
    expected = GraphSnapshot(
        source="expected",
        entities=(GraphEntity("Client 4021", kind="client", account_last4="4021"),),
        relations=(),
    )
    extracted = GraphSnapshot(
        source="extracted",
        entities=(GraphEntity("Account no. ****4021"),),
        relations=(),
    )
    quality = score_graph_with_account_aliases(extracted, expected)
    assert quality.quality.matched_entities == 0
    assert quality.alias_credited_nodes == 0


def test_graph_retriever_maps_ranked_file_paths_to_original_citation_chunks(tmp_path):
    chunks = {
        "doc_a#c0": Chunk(
            chunk_id="doc_a#c0",
            doc_id="doc_a",
            text="Exact source text A",
            page=1,
            char_start=0,
            char_end=19,
        ),
        "doc_b#c0": Chunk(
            chunk_id="doc_b#c0",
            doc_id="doc_b",
            text="Exact source text B",
            page=1,
            char_start=0,
            char_end=19,
        ),
    }
    calls = []

    def query_data(query, mode, k):
        calls.append((query, mode, k))
        return {
            "status": "success",
            "data": {
                "chunks": [{"file_path": "doc_b", "content": "provider copy"}],
                "relationships": [{"file_path": "doc_a<SEP>unknown_doc"}],
                "entities": [],
                "references": [],
            },
        }

    retriever = LightRAGRetriever(
        index_dir=tmp_path,
        working_dir=tmp_path,
        model="ollama/qwen3:8b",
        embedding_model="nomic-embed-text",
        embedding_dim=768,
        base_url="http://localhost:11434",
        query_mode="global",
        query_data_fn=query_data,
        chunks=chunks,
    )
    hits = retriever.retrieve("summarize", k=2)
    assert calls == [("summarize", "global", 2)]
    assert [hit.chunk.chunk_id for hit in hits] == ["doc_b#c0", "doc_a#c0"]
    assert [hit.chunk.text for hit in hits] == ["Exact source text B", "Exact source text A"]
    assert [hit.source for hit in hits] == ["lightrag_global", "lightrag_global"]
    assert [hit.score for hit in hits] == [1.0, 0.5]


def test_graph_retriever_exposes_local_mode_and_rejects_failed_query(tmp_path):
    chunk = Chunk(
        chunk_id="doc_a#c0",
        doc_id="doc_a",
        text="Evidence",
        page=1,
        char_start=0,
        char_end=8,
    )
    modes = []

    def query_data(query, mode, k):
        modes.append(mode)
        return {"status": "success", "data": {"chunks": [{"file_path": "doc_a"}]}}

    retriever = LightRAGRetriever(
        index_dir=tmp_path,
        working_dir=tmp_path,
        model="ollama/qwen3:8b",
        embedding_model="nomic-embed-text",
        embedding_dim=768,
        base_url="http://localhost:11434",
        query_data_fn=query_data,
        chunks={chunk.chunk_id: chunk},
    )
    assert retriever.retrieve_mode("detail", mode="local", k=1)[0].chunk == chunk
    assert modes == ["local"]

    retriever._query_data_fn = lambda query, mode, k: {
        "status": "failure",
        "message": "keyword extraction failed",
    }
    with pytest.raises(RuntimeError, match="keyword extraction failed"):
        retriever.retrieve("broken", k=1)


def test_matrix_cli_exposes_graph_variant_and_global_summary_population():
    args = build_eval_parser().parse_args(
        [
            "matrix",
            "--models",
            "ollama/qwen3:8b",
            "--variants",
            "B_hybrid",
            "C_graph",
            "--categories",
            "global_summary",
            "--limit",
            "0",
            "--graph-answer-top-n",
            "6",
        ]
    )
    assert args.variants == ["B_hybrid", "C_graph"]
    assert args.categories == ["global_summary"]
    assert args.limit == 0
    assert args.graph_answer_top_n == 6


def test_graph_context_budget_override_is_explicit_and_variant_scoped():
    cfg = load_config()
    assert _answer_top_n(cfg, "C_graph") == 12
    assert _answer_top_n(cfg, "C_graph", graph_answer_top_n=6) == 6
    assert _answer_top_n(cfg, "B_hybrid", graph_answer_top_n=12) == 6


def test_graphml_adapter_preserves_nodes_edges_and_source_doc_ids(tmp_path):
    graph = nx.Graph()
    graph.add_node(
        "Priya Raman",
        entity_type="PERSON",
        description="Consultant",
        file_path="inv_priya_01.pdf<SEP>inv_priya_02.pdf",
    )
    graph.add_node("Cedar Grove Media", entity_type="ORGANIZATION")
    graph.add_edge(
        "Priya Raman",
        "Cedar Grove Media",
        keywords="invoiced",
        source_id="inv_priya_01-chunk-000",
        file_path="inv_priya_01",
    )
    path = tmp_path / "graph.graphml"
    nx.write_graphml(graph, path)
    loaded = load_lightrag_graphml(path)
    assert loaded.source == "lightrag:graph.graphml"
    assert loaded.entities[1].name == "Priya Raman"
    assert loaded.entities[1].source_doc_ids == ("inv_priya_01", "inv_priya_02")
    assert loaded.relations[0].predicate == "invoiced"
    assert loaded.relations[0].evidence_doc_ids == ("inv_priya_01",)


def test_lightrag_inputs_preserve_one_document_id_per_source():
    ids, documents = documents_from_chunks(REPO_ROOT / "data" / "index")
    assert len(ids) == len(documents) == 60
    index = ids.index("f1099_cedargrove_priya_2024")
    assert "Priya Raman" in documents[index]


def test_receipt_path_can_describe_repo_and_disposable_indexes(tmp_path):
    repo_file = REPO_ROOT / "data" / "index" / "chunks.jsonl"
    assert _display_path(repo_file, REPO_ROOT) == "data/index/chunks.jsonl"
    external = tmp_path / "graph.graphml"
    assert _display_path(external, REPO_ROOT) == str(external)


def test_local_binding_disables_thinking_and_maps_json_mode():
    payload = _chat_payload(
        model="ollama/qwen3:8b",
        prompt="extract",
        system_prompt="system",
        history_messages=[{"role": "assistant", "content": "prior"}],
        response_format={"type": "json_object"},
        max_tokens=512,
    )
    assert payload["model"] == "qwen3:8b"
    assert payload["think"] is False
    assert payload["format"] == "json"
    assert payload["options"]["num_predict"] == 512
    assert [message["role"] for message in payload["messages"]] == [
        "system",
        "assistant",
        "user",
    ]


def test_obsidian_export_writes_every_entity_and_document_with_cross_links(tmp_path):
    graph = _ground_truth()
    doc_ids = _doc_ids()
    summary = export_obsidian_vault(graph, document_ids=doc_ids, output_dir=tmp_path)
    assert summary == {
        "source": "ground_truth",
        "entities": 15,
        "relations": 15,
        "documents": 60,
    }
    assert len(list((tmp_path / "entities").glob("*.md"))) == 15
    assert len(list((tmp_path / "documents").glob("*.md"))) == 60
    readme = (tmp_path / "README.md").read_text()
    assert "not LightRAG extraction evidence" in readme
    priya = (tmp_path / "entities" / "priya-raman.md").read_text()
    assert "[[entities/cedar-grove-media|Cedar Grove Media]]" in priya
    assert "[[documents/f1099_cedargrove_priya_2024|" in priya
    evidence_doc = (tmp_path / "documents" / "f1099_cedargrove_priya_2024.md").read_text()
    assert "[[entities/priya-raman|Priya Raman]]" in evidence_doc
    assert (tmp_path / ".obsidian" / "graph.json").exists()


def test_obsidian_export_requires_explicit_replace_and_removes_stale_notes(tmp_path):
    graph = GraphSnapshot(
        source="lightrag:test",
        entities=(GraphEntity("Current Entity"),),
        relations=(),
    )
    export_obsidian_vault(graph, document_ids=["doc_a"], output_dir=tmp_path)
    stale = tmp_path / "entities" / "stale.md"
    stale.write_text("stale")
    with pytest.raises(FileExistsError, match="replace=True"):
        export_obsidian_vault(graph, document_ids=["doc_a"], output_dir=tmp_path)
    export_obsidian_vault(
        graph,
        document_ids=["doc_a"],
        output_dir=tmp_path,
        replace=True,
    )
    assert not stale.exists()
    assert (tmp_path / "entities" / "current-entity.md").exists()


def test_obsidian_export_keeps_distinct_entities_when_slugs_collide(tmp_path):
    graph = GraphSnapshot(
        source="lightrag:test",
        entities=(GraphEntity("Account"), GraphEntity("ACCOUNT")),
        relations=(GraphRelation("Account", "distinct from", "ACCOUNT"),),
    )
    summary = export_obsidian_vault(graph, document_ids=[], output_dir=tmp_path)
    assert summary["entities"] == 2
    notes = sorted(path.name for path in (tmp_path / "entities").glob("*.md"))
    assert notes == ["account--2.md", "account.md"]
    first = (tmp_path / "entities" / "account.md").read_text()
    assert "[[entities/account--2|Account]]" in first
