import pytest
import logging
from sunder.schema import CodeNode, EXTENSION_TO_LANGUAGE
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
        file_path="src/main.py",
        symbol_name="process_payment",
        source_code="def process_payment():\n    verify_user()\n    charge_card()",
        child_nodes=["child_1"],
        parent_nodes=["parent_1"],
        language="python"
    )
    child = CodeNode(
        node_id="child_1",
        file_path="src/auth.py",
        symbol_name="verify_user",
        source_code="def verify_user():\n    return True",
        child_nodes=[],
        parent_nodes=["target_1"],
        language="python"
    )
    parent = CodeNode(
        node_id="parent_1",
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
    """Tests that SQLite's 999 parameter limit is successfully bypassed."""
    # Create 1500 nodes (well over the SQLite limit)
    nodes = [
        CodeNode(
            node_id=f"node_{i}",
            file_path="test.py",
            symbol_name=f"func_{i}",
            source_code="pass",
            language="python"
        )
        for i in range(1500)
    ]
    empty_db.insert_nodes_batch(nodes)
    
    # Attempt to fetch all 1500 at once
    ids_to_fetch = [f"node_{i}" for i in range(1500)]
    retrieved_nodes = empty_db.get_nodes(ids_to_fetch)
    
    assert len(retrieved_nodes) == 1500

def test_db_fuzzy_search(populated_db):
    """Tests FTS5 trigrams, LIKE fallbacks, and keyword collision safety."""
    
    # 1. Trigram search (Standard)
    results = populated_db.fuzzy_search_symbols("payment")
    assert len(results) > 0
    assert results[0][0] == "target_1"
    assert results[0][1] == "process_payment"
    
    # 2. LIKE fallback (< 3 characters)
    results_short = populated_db.fuzzy_search_symbols("pr")
    assert len(results_short) > 0
    assert any(r[1] == "process_payment" for r in results_short)
    
    # 3. FTS5 Reserved Keyword safety (AND / OR)
    populated_db.insert_nodes_batch([CodeNode(
        node_id="keyword_node", file_path="test.py", symbol_name="verify_and_sign", source_code="pass", language="python"
    )])
    
    # If the quotes weren't added in database.py, this would crash with an OperationalError
    results_keyword = populated_db.fuzzy_search_symbols("and")
    assert len(results_keyword) > 0
    assert results_keyword[0][1] == "verify_and_sign"

# --- RETRIEVAL TESTS ---

def test_context_retriever(populated_db):
    retriever = ContextRetriever(populated_db)
    
    blast_radius = retriever.get_blast_radius("target_1")
    
    assert blast_radius.target_node.symbol_name == "process_payment"
    assert len(blast_radius.children) == 1
    assert blast_radius.children[0].symbol_name == "verify_user"
    assert len(blast_radius.parents) == 1
    assert blast_radius.parents[0].symbol_name == "checkout_route"

# --- CONTEXT MANAGER TESTS ---

def test_context_manager_pruning(populated_db):
    retriever = ContextRetriever(populated_db)
    blast_radius = retriever.get_blast_radius("target_1")
    
    # Instantiate manager with an artificially tiny token limit (e.g., 20 tokens)
    # This forces the manager to keep the Target, maybe the Child, but drop the Parent.
    manager = ContextManager(max_tokens=25) 
    
    pruned_context = manager.prune_context(blast_radius)
    
    # Target must always survive
    assert pruned_context.target_node is not None
    # Depending on tiktoken exact counts, parents should be pruned to fit
    assert len(pruned_context.parents) == 0

# --- INGESTION TESTS (THE LANGUAGE STRESS TEST) ---

def test_ingest_all_languages(tmp_path, empty_db, caplog):
    """
    Creates a dummy file for EVERY language defined in schema.py and attempts ingestion.
    This will reveal which Tree-sitter grammars are missing in your local environment.
    """
    # Create a dummy file for every extension
    for ext, lang in EXTENSION_TO_LANGUAGE.items():
        dummy_file = tmp_path / f"dummy{ext}"
        # A generic syntax that won't crash basic parsers immediately
        dummy_file.write_text(f"// Dummy file for {lang}\nfunction generic_test() {{ return 1; }}")
        
    engine = IngestionEngine(empty_db)
    
    # Capture warnings and errors during ingestion
    with caplog.at_level(logging.WARNING):
        engine.ingest_repository(str(tmp_path))

    # Query the DB to see what ACTUALLY made it in
    cursor = empty_db.conn.cursor()
    cursor.execute("SELECT DISTINCT language FROM code_nodes")
    succeeded_langs = [row["language"] for row in cursor.fetchall()]
    
    # Collect the failures
    failed_logs = [record.message for record in caplog.records if "Error parsing" in record.message or "Error loading" in record.message]

    # --- CLI OUTPUT FORMATTING ---
    print("\n" + "="*50)
    print("TREE-SITTER GRAMMAR DIAGNOSTICS")
    print("="*50)
    
    print("\n✅ SUCCESSFULLY LOADED & PARSED:")
    for lang in sorted(succeeded_langs):
        print(f"  - {lang}")
        
    print("\n❌ FAILED (Missing Grammar or Parse Error):")
    if not failed_logs:
        print("  None! All languages are supported on this machine.")
    else:
        for log in failed_logs:
            print(f"  - {log}")
            
    print("="*50 + "\n")
    
    # We do NOT assert that all languages passed, because the point of this test
    # is to observe your local system's capabilities.
    assert len(succeeded_langs) > 0, "At least some core languages should have parsed."