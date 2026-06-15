import os
import pytest
import logging
from sunder.schema import CodeNode, NodeType, EXTENSION_TO_LANGUAGE, BlastRadiusContext
from sunder.knowledge.database import KnowledgeDatabase
from sunder.knowledge.ingestion import IngestionEngine
from sunder.knowledge.retrieval import ContextRetriever
from sunder.knowledge.context_manager import ContextManager

# --- FIXTURES ---

@pytest.fixture
def empty_db():
    """Provides a fresh in-memory database for each test."""
    return KnowledgeDatabase()

@pytest.fixture
def populated_db(empty_db):
    """Provides a database pre-populated with a target, parent, and child node."""
    target = CodeNode(
        node_id="target_1",
        node_type=NodeType.FUNCTION,
        file_path="src/main.py",
        symbol_name="process_payment",
        source_code="def process_payment():\n    verify_user()\n    charge_card()",
        child_nodes=["child_1"],
        parent_nodes=["parent_1"],
        language="python"
    )
    child = CodeNode(
        node_id="child_1",
        node_type=NodeType.FUNCTION,
        file_path="src/auth.py",
        symbol_name="verify_user",
        source_code="def verify_user():\n    return True",
        child_nodes=[],
        parent_nodes=["target_1"],
        language="python"
    )
    parent = CodeNode(
        node_id="parent_1",
        node_type=NodeType.METHOD,
        file_path="src/api.py",
        symbol_name="checkout_route",
        source_code="def checkout_route():\n    process_payment()",
        child_nodes=["target_1"],
        parent_nodes=[],
        language="python"
    )
    empty_db.insert_nodes_batch([target, child, parent])
    return empty_db

# --- DATABASE TESTS ---

def test_db_batch_insert_and_get(empty_db):
    node = CodeNode(
        node_id="test_uuid",
        node_type=NodeType.FUNCTION,
        file_path="test.py",
        symbol_name="test_func",
        source_code="pass",
        child_nodes=["a"],
        parent_nodes=["b"],
        language="python"
    )
    empty_db.insert_nodes_batch([node])
    
    retrieved = empty_db.get_node("test_uuid")
    assert retrieved is not None
    assert retrieved.symbol_name == "test_func"
    assert retrieved.child_nodes == ["a"]

def test_db_get_nodes_chunking(empty_db):
    """Tests that SQLite's parameter limits are bypassed via explicit chunking."""
    nodes = [
        CodeNode(
            node_id=f"node_{i}",
            node_type=NodeType.FUNCTION,
            file_path="test.py",
            symbol_name=f"func_{i}",
            source_code="pass",
            language="python"
        )
        for i in range(1500)
    ]
    empty_db.insert_nodes_batch(nodes)
    
    ids_to_fetch = [f"node_{i}" for i in range(1500)]
    retrieved_nodes = empty_db.get_nodes(ids_to_fetch)
    
    assert len(retrieved_nodes) == 1500

def test_db_fuzzy_search_join(populated_db):
    """Tests FTS5 trigrams, LIKE fallbacks, and the relational JOIN for UI metadata."""
    
    # 1. Trigram search (Standard) - Expecting the new 4-tuple
    results = populated_db.fuzzy_search_symbols("payment")
    assert len(results) > 0
    assert len(results[0]) == 4, "Search should return a 4-tuple for the UI."
    assert results[0][0] == "target_1"
    assert results[0][1] == "process_payment"
    assert results[0][2] == NodeType.FUNCTION
    assert results[0][3] == "src/main.py"
    
    # 2. LIKE fallback (< 3 characters)
    results_short = populated_db.fuzzy_search_symbols("pr")
    assert len(results_short) > 0
    assert any(r[1] == "process_payment" for r in results_short)
    
    # 3. FTS5 Reserved Keyword safety (AND / OR)
    populated_db.insert_nodes_batch([CodeNode(
        node_id="keyword_node", node_type=NodeType.FUNCTION, file_path="test.py", symbol_name="verify_and_sign", source_code="pass", language="python"
    )])
    
    results_keyword = populated_db.fuzzy_search_symbols("and")
    assert len(results_keyword) > 0
    assert results_keyword[0][1] == "verify_and_sign"

# --- RETRIEVAL TESTS ---

def test_context_retriever(populated_db):
    """Tests that Phase 1 Retrieval accurately stubs children/parents."""
    retriever = ContextRetriever(populated_db)
    
    blast_radius = retriever.get_blast_radius("target_1")
    
    assert blast_radius.target_node.symbol_name == "process_payment"
    assert len(blast_radius.children) == 1
    assert len(blast_radius.parents) == 1

def test_context_retriever_phase_1(empty_db):
    """
    Tests that Phase 1 Retrieval accurately handles nodes without resolved dependencies.
    Simulates the exact output of the Phase 1 IngestionEngine.
    """
    phase_1_target = CodeNode(
        node_id="target_phase_1",
        node_type=NodeType.FUNCTION,
        file_path="src/main.py",
        symbol_name="process_payment",
        source_code="def process_payment():\n    verify_user()\n    charge_card()",
        child_nodes=[],   
        parent_nodes=[],  
        language="python"
    )
    empty_db.insert_nodes_batch([phase_1_target])
    
    retriever = ContextRetriever(empty_db)
    blast_radius = retriever.get_blast_radius("target_phase_1")
    
    assert blast_radius.target_node.symbol_name == "process_payment"
    assert len(blast_radius.children) == 0, "Phase 1 nodes should have 0 children resolved."
    assert len(blast_radius.parents) == 0, "Phase 1 nodes should have 0 parents resolved."

# --- CONTEXT MANAGER TESTS ---

def test_context_manager_size_sorting(populated_db):
    """
    Tests the optimization that prioritizes smaller chunks.
    A massive child placed FIRST in the array should be skipped,
    while a tiny child placed LAST should successfully pack into the limited context.
    """
    target = populated_db.get_node("target_1")
    
    huge_child = CodeNode(
        node_id="huge", node_type=NodeType.CLASS, file_path="src/db.py", 
        symbol_name="GodClass", source_code="def x():\n    pass\n" * 500, language="python"
    )
    tiny_child = CodeNode(
        node_id="tiny", node_type=NodeType.FUNCTION, file_path="src/util.py", 
        symbol_name="tiny", source_code="def tiny(): pass", language="python"
    )

    manual_blast_radius = BlastRadiusContext(
        target_node=target,
        children=[huge_child, tiny_child], # Huge is strategically placed first
        parents=[]
    )
    
    # Max tokens large enough for Target + Tiny, but NOT Target + Huge
    manager = ContextManager(max_tokens=150) 
    pruned_context = manager.prune_context(manual_blast_radius)
    
    assert pruned_context.target_node is not None
    assert len(pruned_context.children) == 1
    assert pruned_context.children[0].node_id == "tiny", "Manager failed to sort by size and pack the tiny node."

# --- INGESTION TESTS ---

def test_ingestion_relative_paths_and_uuids(tmp_path, empty_db):
    """Tests that ingestion strips absolute paths, preventing AI context leaks and broken deterministic UUIDs."""
    engine = IngestionEngine(empty_db)
    
    # Create a nested dir to test relative resolution
    nested_dir = tmp_path / "src" / "api"
    nested_dir.mkdir(parents=True)
    target_file = nested_dir / "test.py"
    target_file.write_text("def my_func(): pass")
    
    engine.ingest_repository(str(tmp_path))
    
    cursor = empty_db.conn.cursor()
    cursor.execute("SELECT file_path FROM code_nodes LIMIT 1")
    row = cursor.fetchone()
    
    assert row is not None
    # Ensure it's 'src/api/test.py' or 'src\api\test.py', NOT '/tmp/pytest-of.../src/api/test.py'
    assert "pytest" not in row["file_path"]
    assert row["file_path"].startswith("src")

def test_ingest_all_languages(tmp_path, empty_db, caplog):
    """
    Creates valid dummy files for core languages and generic files for others.
    """
    VALID_SYNTAX = {
        ".py": "def generic_test():\n    return 1",
        ".js": "function generic_test() { return 1; }",
        ".ts": "function generic_test(): number { return 1; }",
        ".go": "func generic_test() int { return 1 }",
        ".rs": "fn generic_test() -> i32 { 1 }",
        ".java": "class Test { void generic_test() {} }",
        ".c": "int generic_test() { return 1; }",
        ".cpp": "int generic_test() { return 1; }",
    }

    for ext, lang in EXTENSION_TO_LANGUAGE.items():
        dummy_file = tmp_path / f"dummy{ext}"
        code = VALID_SYNTAX.get(ext, f"// Dummy file for {lang}\nfunction generic_test() {{ return 1; }}")
        dummy_file.write_text(code)
        
    engine = IngestionEngine(empty_db)
    
    with caplog.at_level(logging.WARNING):
        engine.ingest_repository(str(tmp_path))

    cursor = empty_db.conn.cursor()
    cursor.execute("SELECT DISTINCT language FROM code_nodes")
    succeeded_langs = [row["language"] for row in cursor.fetchall()]
    
    skipped_logs = [record.message for record in caplog.records if "Skipping" in record.message]

    print("\n" + "="*50)
    print("TREE-SITTER GRAMMAR DIAGNOSTICS (PHASE 1)")
    print("="*50)
    
    print("\n SUCCESSFULLY EXTRACTED NODES:")
    for lang in sorted(succeeded_langs):
        print(f"  - {lang}")
        
    print("\n  SKIPPED (Missing Parser or Incompatible Queries):")
    if not skipped_logs:
        print("  None! All languages perfectly aligned.")
    else:
        for log in skipped_logs:
            print(f"  - {log}")
    print("="*50 + "\n")
    
    assert len(succeeded_langs) > 0, "At least some core languages should have parsed."