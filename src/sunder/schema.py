from typing import List, Dict, Optional
from pydantic import BaseModel, Field, SecretStr
from enum import Enum

# =================================
# Knowledge Layer schemas
# =================================

class NodeType(str, Enum):
    FUNCTION = "function"
    METHOD = "method"
    CLASS = "class"

class CodeNode(BaseModel):
    """Represents a single logical chunk of the enterprise codebase."""
    node_id: str = Field(
        description="Unique UUID for the AST chunk."
    )
    node_type: NodeType = Field(
        default=NodeType.FUNCTION, 
        description="Categorizes the node to determine prompt structure."
    )
    file_path: str = Field(
        description="Relative path in the repository (e.g., src/auth/jwt.py)."
    )
    symbol_name: str = Field(
        description="Name of the function or class."
    )
    source_code: str = Field(
        description="The actual raw text of the code chunk."
    )
    child_nodes: List[str] = Field(
        default_factory=list, 
        description="UUIDs of functions that this node explicitly calls. These dependencies should typically be mocked."
    )
    parent_nodes: List[str] = Field(
        default_factory=list, 
        description="UUIDs of functions throughout the repository that call this node. Use these to understand realistic input structures."
    )
    language: str = Field(
        description="The programming language of this code chunk (e.g., 'python', 'javascript', 'go')."
    )

# =================================
# Execution Layer schemas
# =================================

class NetworkMode(str, Enum):
    NONE = "none"
    BRIDGE = "bridge"

class SandboxProfile(BaseModel):
    """Configuration object managed by the TUI and enforced by the Execution Layer."""
    network_mode: NetworkMode = Field(
        default=NetworkMode.NONE,
        description="Determines if the container has network access. 'none' enforces absolute isolation."
    )
    memory_limit: str = Field(
        default="512m",
        description="Maximum RAM allocated to the test container (e.g., '256m', '1g')."
    )
    cpu_quota: float = Field(
        default=1.0,
        description="Fractional CPU cores allocated to the test container (e.g., 1.0 for one core)."
    )
    timeout_seconds: int = Field(
        default=30,
        description="Maximum allowed execution time in seconds before the container is forcibly killed by the host."
    )
    environment_vars: Dict[str, str] = Field(
        default_factory=dict,
        description="Key-value pairs of environment variables injected into the container (e.g., configuration overrides or poison pill credentials)."
    )
    custom_image: str = Field(
        default=None,
        description="The name of the pre-built Docker image to use. Passed down by the Bootstrapper."
    )

class ExecutionReport(BaseModel):
    """Raw data returned from the Docker Sandbox."""
    exit_code: int = Field(
        description="The integer exit code returned by the test execution."
    )
    stdout: str = Field(
        description="The standard terminal output generated during the test run."
    )
    stderr: str = Field(
        description="The error traces, panic logs, or warnings generated during the test run."
    )
    duration_seconds: float = Field(
        default=0.0,
        description="The total time taken for the sandbox execution."
    )
    oom_killed: bool = Field(
        default=False,
        description="True if the Docker container was killed for exceeding memory limits."
    )
    timed_out: bool = Field(
        default=False,
        description="True if the execution hit the timeout_seconds limit and was killed by the host."
    )

# =================================
# Orchestration Layer schemas
# =================================

class AgentMode(str, Enum):
    BASELINE = "baseline"
    ADVERSARIAL = "adversarial"

class BlastRadiusContext(BaseModel):
    """The packaged context delivered to the Orchestration Layer."""
    target_node: CodeNode = Field(
        description="The primary function or class being tested by the agent."
    )
    children: List[CodeNode] = Field(
        description="Dependencies and functions explicitly called by the target node. These should be mocked."
    )
    parents: List[CodeNode] = Field(
        description="Functions that call the target node. These provide examples of realistic input structures and usage patterns."
    )

class EnvironmentState(BaseModel):
    """Persistent data object generated during Baseline Mode."""
    auth_headers: Dict[str, SecretStr] = Field(
        default_factory=dict,
        description="Generated JWTs, session IDs, or Bearer tokens required to bypass authentication checks."
    )
    seeded_entities: Dict[str, str] = Field(
        default_factory=dict,
        description="Key-value map of mock database IDs initialized during the Baseline test (e.g., {'test_user_id': 'uuid-123'})."
    )
    cookies: Dict[str, SecretStr] = Field(
        default_factory=dict, 
        description="Session cookies required for web-based auth barriers."
    )
    mock_credentials: Dict[str, SecretStr] = Field(
        default_factory=dict, 
        description="Plaintext username/passwords created by the Baseline test for the AI to use in payloads."
    )
    dynamic_endpoints: Dict[str, str] = Field(
        default_factory=dict, 
        description="Host/Port mappings if docker-compose spins up dependencies dynamically (e.g., {'redis': 'localhost:6379'})."
    )
    ephemeral_files: List[str] = Field(
        default_factory=list, 
        description="Paths to temporary files generated by the Baseline test that the Adversary test might need to read."
    )

class AgentStatus(str, Enum):
    PENDING = "pending"
    COMPLETED = "completed"
    FAILED = "failed"

class EvaluationVerdict(str, Enum):
    """The internal conclusion reached by the LangGraph Evaluator node."""
    SYSTEM_SECURE = "SYSTEM_SECURE"
    VULNERABILITY_FOUND = "VULNERABILITY_FOUND"
    SYNTAX_ERROR = "SYNTAX_ERROR"

class SunderAgentState(BaseModel):
    """The mutable state object passed between nodes in the LangGraph state machine."""
    mode: AgentMode = Field(
        description="The current operational mode of the agent ('baseline' for state seeding, 'adversarial' for fuzzing)."
    )
    context: BlastRadiusContext = Field(
        description="The structural code context defining the target and its relational blast radius."
    )
    sandbox_config: SandboxProfile = Field(
        description="The strict execution constraints applied to the zero-trust Docker sandbox."
    )
    env_state: EnvironmentState = Field(
        default_factory=EnvironmentState,
        description="The persistent state containing dynamic credentials, mock data, and routing endpoints passed between test iterations."
    )
    current_test_script: str = Field(
        default="",
        description="The raw code of the latest AI-generated test script."
    )
    execution_report: Optional[ExecutionReport] = Field(
        default=None,
        description="The structured output from the most recent sandbox run. Null if no execution has occurred yet."
    )
    evaluator_feedback: str = Field(
        default="",
        description="Actionable synthesis provided by the Evaluator node to guide the Coder node in fixing bugs or adapting the next payload."
    )
    retry_count: int = Field(
        default=0,
        description="The current iteration number of the agentic loop. Used by the router to prevent infinite loops."
    )
    max_retries: int = Field(
        default=3,
        description="The maximum number of times the Evaluator will route back to a Coder node before forcing termination."
    )
    status: AgentStatus = Field(
        default=AgentStatus.PENDING,
        description="The overarching status of the LangGraph state machine execution."
    )
    final_verdict: Optional[EvaluationVerdict] = Field(
        default=None,
        description="The final conclusion reached by the Evaluator node upon completion."
    )
    internal_system_error: Optional[str] = Field(
        default=None,
        description="Captures host-level errors (e.g., Docker daemon unreachable, AST parsing failure) to safely abort the graph."
    )

# ==========================================
# Orchestration LLM Output Schemas
# ==========================================

class CoderOutput(BaseModel):
    """Strict output schema for the Baseline and Adversarial Coder nodes."""
    test_script: str = Field(
        description=(
            "The complete, fully executable test script code. "
            "Do NOT include markdown formatting (like ```python). "
            "Output strictly the raw source code."
        )
    )

class BaselineEvaluatorOutput(BaseModel):
    """Strict output schema for the Baseline Evaluator."""
    verdict: EvaluationVerdict = Field(
        description="The formal conclusion of the baseline execution."
    )
    feedback: str = Field(
        default="",
        description=(
            "If SYNTAX_ERROR, explain how to fix the test script. "
            "If VULNERABILITY_FOUND, explain the application crash. "
            "Leave empty if SYSTEM_SECURE."
        )
    )
    extracted_auth_headers: Dict[str, str] = Field(
        default_factory=dict,
        description="If SYSTEM_SECURE, extract printed JWTs or Bearer tokens here. Otherwise, empty."
    )
    extracted_seeded_entities: Dict[str, str] = Field(
        default_factory=dict,
        description="If SYSTEM_SECURE, extract printed mock database IDs here. Otherwise, empty."
    )
    extracted_cookies: Dict[str, str] = Field(
        default_factory=dict,
        description="If SYSTEM_SECURE, extract printed session cookies here. Otherwise, empty."
    )
    extracted_mock_credentials: Dict[str, str] = Field(
        default_factory=dict,
        description="If SYSTEM_SECURE, extract printed mock username/passwords here. Otherwise, empty."
    )
    extracted_dynamic_endpoints: Dict[str, str] = Field(
        default_factory=dict,
        description="If SYSTEM_SECURE, extract printed dynamic host/port mappings here. Otherwise, empty."
    )
    extracted_ephemeral_files: List[str] = Field(
        default_factory=list,
        description="If SYSTEM_SECURE, extract printed paths to generated temporary files here. Otherwise, empty."
    )

class AdversaryEvaluatorOutput(BaseModel):
    """Strict output schema for the Adversary Evaluator."""
    verdict: EvaluationVerdict = Field(
        description="The formal conclusion of the adversarial execution."
    )
    feedback: str = Field(
        default="",
        description=(
            "If SYNTAX_ERROR, explain how to fix the code. "
            "If SYSTEM_SECURE, suggest a brief new attack vector for the next payload. "
            "Leave empty if VULNERABILITY_FOUND."
        )
    )

# =================================
# Constants
# =================================

# Map file extensions to Tree-sitter language identifiers (Aligned with Helix Queries)
EXTENSION_TO_LANGUAGE = {
    # Core languages
    ".py": "python",
    ".js": "javascript",
    ".ts": "typescript",
    ".go": "go",
    ".java": "java",
    ".rs": "rust",
    ".c": "c",
    ".h": "c",          
    ".cpp": "cpp",
    ".hpp": "cpp",      
    ".cs": "c-sharp",   
    ".rb": "ruby",

    # Enterprise & Mobile
    ".kt": "kotlin",
    ".swift": "swift",
    
    # Web & Scripting
    ".php": "php",
    ".dart": "dart",
    ".t": "perl",
    ".lua": "lua",
    ".R": "r",

    # Functional & Concurrency
    ".exs": "elixir",
    ".ex": "elixir",   
    ".erl": "erlang",
    ".hs": "haskell",
    ".scala": "scala",

    # Infrastructure & Systems
    ".bats": "bash",   
    ".sh": "bash"       
}

# Skip folders that are commonly ignored during code analysis
SKIP_FOLDERS = {
    # Python (.py)
    "__pycache__",
    "venv",
    "env",
    "htmlcov",
    "site-packages",
    "eggs",
    "wheels",
    
    # JavaScript / TypeScript / Web (.js, .ts, .css, .html)
    "node_modules",
    "bower_components",
    "dist",
    "out",
    "build",
    "coverage",
    
    # Go / PHP / Ruby (.go, .php, .rb)
    "vendor",
    "bundle",
    
    # Java / Kotlin / Scala (.java, .kt, .scala)
    "target",
    "bin",
    
    # C / C++ / C# / Rust (.c, .cpp, .cs, .rs)
    "obj",
    "Debug",
    "Release",
    "cmake-build-debug",
    "cmake-build-release",
    
    # Mobile (Swift / Objective-C)
    "Carthage",
    "Pods",
    "DerivedData",
    
    # Dart / Flutter (.dart)
    "tool",
    
    # Perl / Lua / R (.t, .lua, .R)
    "blib",
    "lua_modules",
    
    # Functional (Elixir, Erlang, Haskell)
    "_build",
    "deps",
    "dist-newstyle"
}

# A map to resolve Tree-sitter language IDs to conventional test file extensions
LANGUAGE_EXTENSION_MAP = {
    # Core languages
    "python": ".py",              # Pytest / Unittest
    "javascript": ".test.js",     # Jest / Mocha
    "typescript": ".test.ts",     # Jest
    "go": "_test.go",             # `go test` convention
    "java": "Test.java",          # JUnit convention (must match class name)
    "ruby": "_spec.rb",           # RSpec convention (or _test.rb for Minitest)
    "rust": ".rs",                # Cargo test (usually integrated or tests/ folder)
    "c": ".c",                    # Unity / CMocka
    "cpp": ".cpp",                # Google Test / Catch2
    "c-sharp": "Tests.cs",        # xUnit / NUnit (Aligned with Helix)

    # Enterprise & Mobile
    "kotlin": "Test.kt",          # JUnit / Kotest
    "swift": "Tests.swift",       # XCTest
    # "objective_c": "Tests.m",   # Commented out as Helix lacks default queries
    
    # Web & Scripting
    "php": "Test.php",            # PHPUnit
    "dart": "_test.dart",         # Dart test / Flutter test
    "perl": ".t",                 # Test::More (standard Perl testing)
    "lua": "_spec.lua",           # Busted (Lua testing framework)
    "r": "test.R",                # testthat

    # Functional & Concurrency
    "elixir": "_test.exs",        # ExUnit
    "erlang": "_SUITE.erl",       # Common Test
    "haskell": "Spec.hs",         # Hspec
    "scala": "Spec.scala",        # ScalaTest

    # Infrastructure & Systems
    "bash": ".bats",              # Bash Automated Testing System (Aligned with Helix)
}

# Commands used to execute the AI-generated test script after the ephemeral workspace is staged
LANGUAGE_RUN_COMMANDS = {
    # Core languages
    "python": "python sunder_generated_test.py",
    "javascript": "node sunder_generated_test.test.js",
    "typescript": "npx -y tsx sunder_generated_test.test.ts",
    "go": "go test sunder_generated_test_test.go",
    "java": "java sunder_generated_testTest.java",  # Relies on Java 11+ single-file source execution
    "rust": "rustc sunder_generated_test.rs && ./sunder_generated_test",
    "c": "gcc sunder_generated_test.c -o test_bin && ./test_bin",
    "cpp": "g++ sunder_generated_test.cpp -o test_bin && ./test_bin",
    "c-sharp": "csc sunder_generated_testTests.cs && mono sunder_generated_testTests.exe", 
    "ruby": "ruby sunder_generated_test_spec.rb",

    # Enterprise & Mobile
    "kotlin": "kotlinc sunder_generated_testTest.kt -include-runtime -d test.jar && java -jar test.jar",
    "swift": "swift sunder_generated_testTests.swift",
    
    # Web & Scripting
    "php": "php sunder_generated_testTest.php",
    "dart": "dart test sunder_generated_test_test.dart",
    "perl": "perl sunder_generated_test.t",
    "lua": "lua sunder_generated_test_spec.lua",
    "r": "Rscript sunder_generated_testtest.R",

    # Functional & Concurrency
    "elixir": "elixir sunder_generated_test_test.exs",
    "erlang": "erlc sunder_generated_test_SUITE.erl && erl -noshell -s sunder_generated_test_SUITE test -s init stop",
    "haskell": "runhaskell sunder_generated_testSpec.hs",
    "scala": "scala sunder_generated_testSpec.scala",

    # Infrastructure & Systems
    "bash": "bats sunder_generated_test.bats"
}