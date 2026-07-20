# System Architecture: Sunder

This is the architectural documentation for **Sunder**. This document provides a comprehensive overview of the system's design principles, constraints, data models, and execution flow.

Sunder is engineered as an agentic, zero-trust sandbox testing framework for enterprise codebases. It is designed to evaluate the logic and security of target functions by automatically generating and executing both baseline and adversarial fuzzing tests against an AST-mapped relational context.

It leverages a copy-on-run ephemeral Docker container architecture, Tree-sitter abstract syntax tree parsing, an in-memory SQLite FTS5 database, and a strict Evaluator-Optimizer LangGraph state machine. This was found to be the best approach to guarantee absolute host protection, ensure polyglot compiler compatibility, and eliminate LLM context-window bloat after experimentation with different architectural strategies.

## Table of Contents

1. [Functional Requirements](#1-functional-requirements)
2. [Non-Functional Requirements (NFRs)](#2-non-functional-requirements-nfrs)
3. [Core Entities](#3-core-entities)
4. [High Level Design](#4-high-level-design)
    * [4.1 System Architecture](#41-system-architecture)
    * [4.2 Component Architecture](#42-component-architecture)
    * [4.3 Workflow Data Flow](#43-workflow-data-flow)
5. [Deep Dive](#5-deep-dive)
    * [5.1 Execution Layer Architecture](#51-execution-layer-architecture)
    * [5.2 Knowledge Layer & Relational Retrieval Architecture](#52-knowledge-layer--relational-retrieval-architecture)
    * [5.3 Orchestration Layer Architecture](#53-orchestration-layer-architecture)

---

# 1. Functional Requirements (FRs)

## 1.1. Client Layer (TUI & UX)

1. **Mode Selection:** The system must allow the user to toggle between Baseline Mode (state seeding, happy path, JWT fetching) and Adversarial Mode (chaos fuzzing, logic assertions).

2. **Zero-Trust Configuration Panel:** The TUI must provide a configuration panel with default-secure constraints:

    1. Resource limits (Memory, CPU, Execution timeout).

    2. Network Toggle (Default: OFF).

    3. Environment Variable Injector (Default: Empty/Blocked).

    4. Custom Environment Picker (Allows pointing to custom Dockerfiles or Compose files).

3. **Target Disambiguation (HITL):** If a user searches for a function, the system must pause execution, query the in-memory database, and allow the user to perform a fuzzy search for the target function. It must then display the fixed Context Tree (Target/Parents/Children).

4. **Live Telemetry & Tracing:** The UI must feature a split-pane dashboard rendering the streaming LLM thought/code generation, and the live Docker container logs. Additionally, all agentic steps, LLM calls, and state transitions must be automatically traced and exported to `LangSmith` for deep observability, latency tracking, and debugging.

## 1.2. Knowledge Layer (Context & Retrieval)

1. **AST Ingestion (In-Memory):** The system must parse local repository files into precise structural chunks using a custom `tree-sitter` engine powered by `tags.scm` queries. These nodes are mapped to Sunder's `NodeType` schema and stored in an in-memory SQLite database.

2. **FTS5 Indexing:** The system must utilize SQLite's FTS5 (Full-Text Search) extension to allow instant, zero-dependency text matching.

3. **Blast-Radius Resolution:** Leveraging the relational schema, the system must retrieve the target's source code, the code of the functions it calls (Children), and the code of the functions that call it (Parents).

4. **Token Pruning:** The system must automatically truncate the retrieved context strictly in the order of Target > Immediate Children > Parents if the total token count exceeds the defined limit.

## 1.3. Orchestration Layer (Agent Logic & State)

1. **Structured Prompting:** The Orchestrator must enforce a strict prompt template that segregates the context (e.g., explicitly commanding the LLM to test the Target, mock the Children, and mimic the Parents) to prevent context-window confusion.

2. **Baseline Seeding:** In Baseline mode, the LLM must generate setup code that initializes a mock database state or fetches valid authentication tokens before executing the primary test.

3. **Adversarial Generation:** In Adversarial mode, the LLM must generate malicious inputs and explicitly write `assert` statements to define what constitutes a silent logic failure.

4. **Evaluator Feedback Loop:** The Orchestrator's Evaluator node must parse the raw Docker logs. Instead of feeding massive stack traces back to the Coder, it must use an LLM to synthesize concise, actionable feedback (e.g., _"Mock the Postgres connection"_) and store it in the shared state for the Coder to use on the next iteration.

## 1.4. Execution Layer (Sandbox)

1. **Convention Over Configuration (`.sunder/`):** The system must automatically detect and utilize a `.sunder/Dockerfile` if present in the repository root. If not it must raise and error.

2. **Pre-Flight Builds:** The system must build the Docker image and spin up the background dependency containers (via subprocess) before initiating the LangGraph loop.

3. **Host Protection (Read-Only):** The system must mount the host's enterprise codebase and the test script into the container strictly as read-only volumes.

4. **Copy on Run:** The container must execute a command that copies both the codebase and the test into the same app/ directory such that the tests and the code imports in the test work.

5. **Exit Evaluation:** The Executor node must capture the exit code, `stdout`, and `stderr`, writing them back to the Shared State so the Evaluator can determine if a hard crash (500/OOM), an `AssertionError` (Logic Flaw), or a clean run occurred.

# 2. Non-Functional Requirements (NFRs)

## 2.1. Security & Safety

1. **The Network Kill Switch:** By default, all test execution containers must be launched with `network_mode="none"` to mathematically guarantee no accidental data corruption or external API calls can occur.

2. **Opt-In Privilege Escalation:** Network access and environment variables (production credentials) must only be injected if the user explicitly overrides the defaults via the TUI, shifting the liability of the blast radius to the human operator.

3. **Container Teardown:** The system must reliably destroy all spawned test containers, custom networks, and ephemeral databases the moment the testing loop concludes or the user exits the application.

## 2.2. Performance & Efficiency

1. **Token Economy:** By separating the Build Phase from the Agent Loop, the system must never force the LLM to wait for dependency installation cycles during its iterative testing loops. Furthermore, distilling massive error logs into concise `evaluator_feedback` prevents context window bloat during retries.

2. **Non-Blocking UI:** The Textual TUI must remain responsive and maintain high frame rates while background tasks (like LLM network calls and Docker daemon operations) execute.

3. **Fast Local Ingestion:** By using Tree-sitter and an in-memory SQLite, the codebase indexing process must be fast, avoiding network bottlenecks entirely.

## 2.3. Portability & Agnosticism

1. **Language Agnosticism:** The core agentic loop and retrieval logic must remain independent of specific programming languages, relying entirely on Tree-sitter grammars and custom Docker runtime environments.

2. **Cross-Platform CLI:** Sunder will be distributed as an isolated Python application via `pipx`. This guarantees that its heavy dependencies (LangGraph, Textual, Tree-sitter) do not conflict with the user's system Python packages or the target repository's virtual environment.

## 2.4. Usability & DX (Developer Experience)

1. **Zero-Config Defaults:** Sunder must provide safe, sensible defaults (e.g., 256MB RAM, network off) so a developer can test the tool immediately upon installation without writing custom configurations.

2. **Clear Attribution:** When Sunder declares an Adversarial Success, it must clearly output the specific malicious payload and the resulting crash trace or failed assertion, giving the developer undeniable proof of the vulnerability.

3. **Transparency & Observability:** Sunder must output all of the LLM's generated tokens along with the execution logs in a structured format upon request. Furthermore, deep execution tracing, including the raw prompt inputs, token usage, tool calls, and node-to-node state transitions must be captured via `LangSmith` to ensure complete auditability of the AI's decision-making process.

# 3. Core Entities

## 3.1. CodeNode (The Structural Entity)

Generated via `tree-sitter` and language-specific `tags.scm` queries, and stored as rows in the in-memory SQLite FTS5 database. It represents a single logical chunk of the enterprise codebase (e.g., a function, method, or class).

1. **`node_id`** _(String)_: Unique UUID for the AST chunk.

2. **`node_type`** *(Enum):* `FUNCTION` (default)  |  `METHOD`  |  `CLASS`

3. **`file_path`** _(String)_: Relative path in the repository (e.g., `src/auth/jwt.py`).

4. **`symbol_name`** _(String)_: Name of the function or class.

5. **`source_code`** _(String)_: The actual raw text of the code chunk.

6. **`child_nodes`** _(List[String])_: UUIDs of functions that this node explicitly calls.

7. **`parent_nodes`** _(List[String])_: UUIDs of functions throughout the repository that call this node.

8. **`language`** _(String)_: The programming language of this code chunk (e.g., 'python', 'javascript', 'go').

## 3.2. BlastRadiusContext (The Prompt Entity)

The packaged context delivered to the Orchestration Layer after the user selects a target.

1. **`target_node`** _(CodeNode)_: The specific function the AI must test.

2. **`children`** _(List[CodeNode])_: The dependencies the AI is strictly commanded to mock.

3. **`parents`** _(List[CodeNode])_: The usage examples the AI uses to understand realistic input structures.

## 3.3. SandboxProfile (The Security Entity)

The configuration object managed by the Client Layer (TUI) and enforced by the Execution Layer (Docker).

1. **`network_mode`** _(Enum)_: `NONE` (Default) | `BRIDGE` (Opt-in).

2. **`memory_limit`** _(String)_: Max RAM allocation (default: `512m`).

3. **`cpu_quota`** _(Float)_: Fractional core allocation (default: `1.0`).

4. **`timeout_seconds`** _(Integer)_: Max execution time before Docker SIGKILLs the container (default: `30s`).

5. **`environment_vars`** _(Dict)_: Injected key-value pairs (always empty unless explicitly provided by the user).

6. **`custom_image`** *(String)*: The name of the pre-built Docker image to use. Passed down by the Bootstrapper.

## 3.4. EnvironmentState (The Seed Entity)

The persistent data object generated during **Baseline Mode** and passed into **Adversarial Mode**. It holds the context required to bypass standard access controls and reach deep logic.

1. **`auth_headers`** _(Dict)_: Generated JWTs, Session IDs, or Bearer tokens.

2. **`seeded_entities`** _(Dict)_: Key-value map of mock database IDs (e.g., `{"test_user_id": "uuid-123", "test_cart_id": "uuid-456"}`).

3. **`cookies`** _(Dict)_: Session cookies required for web-based auth barriers.

4. **`mock_credentials`** _(Dict)_: Plaintext username/passwords created by the Baseline test for the AI to use in payloads.

5. **`dynamic_endpoints`** _(Dict)_: Host/Port mappings if dependencies are spun up dynamically.

6. **`ephemeral_files`** _(List[String])_: Paths to temporary files generated by the Baseline test.

## 3.5. SunderAgentState (The Orchestrator Entity)

The mutable state object passed between nodes in the LangGraph state machine. This is the "brain state" of the iterative loop.

1. **`mode`** _(Enum)_: `baseline` | `adversarial`.

2. **`context`** _(BlastRadiusContext)_: The code the AI is looking at.

3. **`sandbox_config`** _(SandboxProfile)_: The rules it must run under.

4. **`env_state`** _(EnvironmentState)_: The seeded credentials.

5. **`current_test_script`** _(String)_: The latest generated test file.

6. **`execution_report`** _(Optional[ExecutionReport])_: The structured output from the most recent sandbox run. Null if no execution has occurred yet.

7. **`exit_code`** *(Integer)*: The exit code from the most recent sandbox run

8. **`evaluator_feedback`** *(String)*: The instructions from the evaluator to the coder nodes.

9. **`retry_count`** _(Integer)_: Current loop iteration (to prevent infinite loops).

10. **`status`** *(Enum)*: `pending` | `completed` | `failed`.

11. **`final_verdict`** *(EvaluationVerdict)*: The final conclusion reached by the Evaluator node upon completion.

12. **`internal_system_error`** _(Optional[String])_: Captures host-level errors (e.g., Docker daemon unreachable, AST parsing failure) to safely abort the graph.

## 3.6. ExecutionReport (The Evaluation Entity)

The raw data returned from the Docker Sandbox, evaluated by LangGraph to determine success or failure.

1. **`exit_code`** _(Integer)_: `0` (Clean run) | `>0` (Crash or Assertion Failure).

2. **`stdout`** _(String)_: Standard terminal output (test runner results).

3. **`stderr`** _(String)_: Error traces and panic logs.

4. **`duration_seconds`** _(Float)_: The total time taken for the sandbox execution.

5. **`oom_killed`** _(Boolean)_: True if the Docker container was killed for exceeding memory limits.

6. **`timed_out`** _(Boolean)_: True if the execution hit the `timeout_seconds` limit and was killed by the host.

## 3.7. EvaluationVerdict (The Judge Entity)

The internal conclusion reached by the LangGraph Evaluator node after parsing the `ExecutionReport`. This drives the conditional routing.

1. **`SYSTEM_SECURE`**: Baseline passed smoothly, or the Adversary payload was handled gracefully by the target application. Sunder exits and submits a report to the user.

2. **`VULNERABILITY_FOUND`**: Adversary caused a hard crash or tripped an adversarial logic assertion. Sunder exits and submits a report to the user.

3. **`SYNTAX_ERROR`**: AI hallucinated a bad test, missed an import, or failed to mock a child dependency. Triggers a self-correction loop via `evaluator_feedback`.

# 4. High Level Design

## 4.1. System Architecture

![Sunder Architecture Diagram](./assets/HLDD.png)

## 4.2. Component Architecture

### 4.2.1. Client Layer

Built using Python’s `Textual` framework, this layer manages the user experience and captures execution boundaries.

1. **Sandbox Config Module:** Manages the Zero-Trust configuration. Captures user inputs for memory limits, network toggles, and environment variable overrides.

2. **HITL Disambiguation View:** Allows the user to select the target function using fuzzy text matching.

3. **Telemetry Dashboard:** A real-time split-pane view rendering the AI's workspace (thoughts/code), the active Context Tree, and the live `stdout/stderr` streams from the Docker daemon.

### 4.2.2. Knowledge Layer

Responsible for mapping and retrieving the semantic and structural relationships within the enterprise codebase without requiring language-specific compilers.

1. **AST Ingestion Engine:** Uses Tree-sitter to parse local repositories into an Abstract Syntax Tree. It chunks code by logical boundaries (functions/classes) and stores them in the local SQLite database utilizing the FTS5 extension for instant full-text search.

2. **Blast-Radius Retriever:** Given a target `node_id`, it executes a multi-pass retrieval to fetch the **Target** (the function itself), the **Children** (dependencies it calls), and the **Parents** (where it is used in the codebase).

3. **Context Manager:** Dynamically prunes the retrieved context to fit the LLM's context window, strictly prioritising the Target and immediate Children over Parent references.

### 4.2.3. Orchestration Layer

The brain of Sunder, built on `LangGraph`. It manages the state machine, asynchronous tool calling, and evaluation loops.

1. **State Object (`SunderAgentState`):** The mutable graph state containing the current mode, the retrieved context, the environment state (JWTs/Mock IDs), the active test script, execution logs, and evaluator feedback.

2. **Structured Prompt Builder:** Assembles the context into rigid prompt templates. It enforces strict boundaries by explicitly commanding the LLM to write tests for the Target while heavily mocking the Children.

3. **Agent Nodes:**

    1. _Baseline Coder:_ Focuses on standard functionality, mocking database states, and fetching valid authentication tokens to prime the environment.

    2. _Adversary Coder:_ Focuses on generating edge-case payloads, malformed inputs, and strict logic-checking `assert` statements.

4. **Evaluator Node:** Analyzes the Docker Execution Report. It routes flow back to the Coders for self-correction (providing synthesised LLM feedback on syntax errors) or terminates the graph and reports a vulnerability (on crashes or tripped assertions).

#### 4.2.3.1. The Nodes

These are the Python functions that perform a single, specific action and update the State.

1. **`BaselineCoder` Node:**

    1. **Role:** The "Happy Path" test writer.

    2. **Action:** Reads the `context` and `evaluator_feedback` (if retrying). Uses the LLM to write a functional test that primes the database and fetches any secrets needed.

    3. **State Update:** Overwrites `current_test_code`.

2. **`AdversaryCoder` Node:**

    1. **Role:** The Fuzzer.

    2. **Action:** Reads the `context`,  `env_state` and `evaluator_feedback` (if retrying). Uses the LLM to write malformed inputs, malicious payloads, and explicit `assert` statements to check for logic flaws.

    3. **State Update:** Overwrites `current_test_code`.

3. **`Executor` Node (NO LLM):**

    1. **Role:** The isolated runner.

    2. **Action:** Reads `current_test_code` and `sandbox_config`. Connects to the Docker Daemon, spins up the container, injects the code, waits for the timeout, and extracts the results.

    3. **State Update:** Overwrites `execution_report`. Increments `retry_count`.

4. **`Evaluator` Node:**

    1. **Role:** The Judge.

    2. **Action:** Reads `current_test_script`, `execution_report`, and `mode`. Uses the LLM to parse stack traces (e.g., figuring out if a failure was a syntax typo, a missing mock, or a genuine vulnerability).

    3. **State Update:** Overwrites `evaluator_feedback` and `evaluator_verdict`. If the Baseline test passed, extracts and saves any required secrets to `env_state`.

#### 4.2.3.2. The Edges

Edges dictate the order of operations. Conditional Edges execute routing logic based on the current State.

##### Standard Edges

1. **`BaselineCoder`** ──> **`Executor`**

2. **`AdversaryCoder`** ──> **`Executor`**

3. **`Executor`** ──> **`Evaluator`**

##### Conditional Edges (The Routing Logic)

1. **`START` ──> `Router`**

    1. _Condition:_ If `state["mode"] == "baseline"`, route to **`BaselineCoder`**.

    2. _Condition:_ If `state["mode"] == "adversarial"`, route to **`AdversaryCoder`**.

2. **`Evaluator` ──> `Decision Engine`**

    1. _Condition A (Timeout/Limit):_ If `state["retry_count"] >= MAX_RETRIES` ──> **`END`**

    2. _Condition B (Baseline Success):_ If mode is `baseline` AND `exit_code == 0` ──> **`END`** (State successfully seeded).

    3. _Condition C (Baseline Failure):_ If mode is `baseline` AND `exit_code > 0` ──> **`BaselineCoder`** (Try to fix the test).

    4. _Condition D (Adversarial Success - Bug Found):_ If mode is `adversarial` AND `exit_code > 0` (Crash/Assert failed) ──> **`END`** (Report vulnerability to UI).

    5. _Condition E (Adversarial Failure - System Secure):_ If mode is `adversarial` AND `exit_code == 0` (Handled gracefully) ──> **`AdversaryCoder`** (Generate a new, different attack vector).

### 4.2.4. Execution Layer (The Zero-Trust Sandbox)

A highly constrained Docker-based execution environment that physically prevents the AI from altering the host machine or accessing unauthorized networks.

1. **Environment Bootstrapper:** Reads the Client Layer's config to spin-up a custom `.sunder/Dockerfile` using the Docker Python SDK.

2. **Host Protection:** Mounts the enterprise repository into the container exclusively as a read-only volume (`mode: 'ro'`).

3. **Test Injection:** Generates a secure temporary directory on the host OS using `tempfile`, writes the generated script, and mounts it into the container at `/app/sunder_test` with `rw` permissions. The directory is aggressively pruned from the host after the container stops.

4. **Constraint Enforcer:** Strictly applies `network_mode="none"` (unless explicitly overridden) and injects "poison pill" environment variables to trap hallucinated database connections.

## 4.3. Workflow Data Flow

Sunder operates in two sequential phases to guarantee deep logic penetration without being blocked by surface-level authentication or state requirements.

### 4.3.1. State Seeding

1. **Target Selection:** The user defines the target function via the TUI.

2. **Context Retrieval:** The Knowledge Layer fetches the Blast-Radius context.

3. **Generation:** The Orchestration Layer prompts the Baseline Agent to write a "Happy Path" test.

4. **Execution:** The Sandbox executes the test.

5. **State Capture:** Upon a clean `exit 0`, the `Evaluator` extracts the generated mock database IDs and valid JWTs, saving them to the `EnvironmentState`.

### 4.3.2. Adversarial Attack

1. **Context Injection:** The Orchestrator prompts the Adversary Agent, injecting the `EnvironmentState` (JWTs/IDs) so the agent can bypass basic auth checks.

2. **Blast-Radius Retrieval:** The Knowledge Layer fetches the full context (Children/Parents) of the target function to build the attack surface.

3. **Weaponization:** The Adversary Agent studies the Parent context (usage patterns) and writes a test script that fuzzes the target with mutated inputs, enforcing `assert` statements to check for illegal state changes.

4. **Isolated Execution:** The Sandbox runs the payload under the specified constraints.

5. **Evaluation:**

    - _If Sandbox exits `>0` due to a crash (SIGSEGV/500):_ Evaluator declares **Success** (Hard vulnerability found).

    - _If Sandbox exits `>0` due to an `AssertionError`:_ Evaluator declares **Success** (Silent logic flaw found).

    - _If Sandbox exits `0` (handled gracefully):_ Evaluator loops back to the Adversary Agent to generate a new attack vector until the retry limit is reached.

# 5. Deep Dive

## 5.1. Execution Layer Architecture

One of the most complex engineering challenges in Sunder’s design was satisfying two competing constraints:

1. **Zero-Trust Host Protection:** The user's enterprise codebase must be mounted as strictly Read-Only (`ro`) so the LLM cannot accidentally delete or corrupt host files.

2. **Native Language Ergonomics:** The AI-generated test script must be able to seamlessly import and execute the enterprise code, regardless of whether the target language is interpreted (Python, JS) or compiled (Go, Rust, C++).

During development, three distinct architectures were evaluated to solve this file-system routing problem:

### 5.1.1. Nested Volume Mounts

The most intuitive approach was to mount the test script directly into the Read-Only project tree.

1. **Mechanism:** Mount the host codebase to `/app` (`ro`). Then, mount the ephemeral test script to a nested subdirectory, `/app/sunder_test` (`rw`).

2. **The Theory:** By placing the test script physically inside the project tree, relative imports (eg:- `from ..src.auth import verify_jwt`) work universally without any configuration.

3. **Why it Failed (Linux File System Physics):** When Docker binds a host directory to `/app`, it completely masks the underlying container image directory. When Docker subsequently tries to attach the nested `/app/sunder_test` mount, it must dynamically create the `sunder_test` folder to serve as the mount point. Because the parent `/app` mount is bound to the host, Docker attempts to execute the `mkdir` command directly on the user's local hard drive. Since the mount mode is `ro`, Docker crashes with a `Read-only file system` error.

### 5.1.2. Side-by-Side Mounts with Environment Injection

To prevent Linux from attempting to write to the host, the architecture was shifted to parallel mounts.

1. **Mechanism:** Mount the enterprise code to `/app` (`ro`) and the test script to an entirely separate directory, `/sunder_test` (`rw`). To allow the test script to "see" the enterprise code, language-specific environment variables (`PYTHONPATH=/app`, `NODE_PATH=/app/node_modules:/app`) are injected into the container at runtime.

2. **The Theory:** The file systems never overlap, mathematically guaranteeing host protection. The interpreter dynamically resolves the imports across the two directories.

3. **Why it Failed (The Compiled Language Barrier):** While this works flawlessly for interpreted languages (Python, Ruby, Node), it completely breaks down for strictly compiled languages like Go and Rust. Compilers resolve modules statically based on directory manifests (e.g., `go.mod`, `Cargo.toml`) and completely ignore runtime environment variables.

### 5.1.3. Copy-on-Run Architecture / Ephemeral Workspace

To achieve true language agnosticism without compromising security, Sunder adopted the copy-on-run architecture.

1. Both the host enterprise code and the temporary test script are mounted into the container as isolated, strictly Read-Only staging directories (`/ro_app` and `/sunder_test`).

2. Sunder parses the target repository's `.gitignore` and combines it with a hardcoded `SKIP_FOLDERS` set (e.g., `node_modules`, `.git`, `target`). These files are added to `tar` exclusion flags so that they are not copied over. `shlex.quote` is used to neuter command injections.

3. Instead of a recursive copy (`cp -a`), Sunder overrides the Docker container's `command` parameter with an in-memory stream injection: `sh -c 'tar -c -C /ro_app {tar_excludes} . | tar -x -C /app && cp /sunder_test/test.* /app/ && <language_run_command>'`

4. The container unpacks the filtered codebase directly into its own ephemeral, Read-Write working directory (`/app`) before executing the compiler/interpreter.

**Advantages:**

1. **Absolute Host Protection:** Both host mounts are mathematically locked as `ro`. The host machine files cannot be changed.

2. **Universal Language Support (Compiler Compatibility):** Because the files are physically extracted side-by-side into `/app` inside the container, Go, Rust, and C++ compilers are perfectly happy. They see a standard, physical project tree (unlike symlinks, which break strict compilers).

3. **Lightning Speed & Dependency Preservation:** By surgically filtering out heavy build folders and datasets via the `.gitignore` integration, the in-memory streaming takes milliseconds. This prevents host files from overwriting the dependencies the user specifically installed via their `.sunder/Dockerfile`.

4. **No Environment Injections:** There is no need to maintain fragile dictionaries of `PYTHONPATH` or `NODE_PATH` injections to bridge the codebase and the test script.

5. **Improved Developer Experience (DX):** The complexity of file routing and exclusion is abstracted entirely away from the user. The user's `.sunder/Dockerfile` is reduced to only pulling an image and optionally installing any dependencies, requiring no boilerplate `CMD`, `WORKDIR`, or volume management.

## 5.2. Knowledge Layer & Relational Retrieval Architecture

### 5.2.1. Vector Search to AST Relational Ingestion

1. The initial architectural for Sunder used a vector database to embed and semantically search code chunks. This approach was discarded because vector embeddings inherently lack structural and semantic relational awareness.

2. A vector search can find functions that *look* textually similar, but it remains blind to the actual relationships between the code such as which function call which functions.

3. To overcome this, Sunder shifted to structural Abstract Syntax Tree (AST) parsing via Tree-sitter, mapping dependencies directly into an in-memory SQLite database utilizing the FTS5 extension. This transforms the context from an isolated function to a function with its dependencies (children) and use cases (parents).

### 5.2.2. Prompting Mechanics of the Blast-Radius Context

Delivering the raw code chunks to an LLM creates severe context confusion and shallow test suites. By structuring a strict prompt template containing the *Target*, its *Children*, and its *Parents*, Sunder maximizes the reasoning capabilities of the agent:

1.   **Target (Objective):** This is the code that the LLM will write the happy-path or adversarial test suite for.

2.   **Children (Mocking):** By looking at the logic of the functions that the target explicitly calls, the LLM can write exact mocks or stubs for these dependencies. This prevents incorrect assumptions about the code and prevents test execution from leaking out into third-party APIs, enforcing the zero-trust containment policy.

3.   **The Parents (Mimicry):** Looking at a function in isolation makes it incredibly difficult for an AI to deduce what real-world arguments look like. Including parent functions (the call sites where the target is actively used throughout the codebase) provides the LLM with production-grade examples. The AI studies these usage patterns to synthesize highly realistic data payloads, along with realistic testing logic that aligns with how the functions is actually used.

### 5.2.3. Engineering Rationale: In-Memory vs. On-Disk SQLite

Once the shift to a relational architecture was finalized, a choice between spinning up a persistent on-disk `.db` file versus using a in-memory (`:memory:`) SQLite instance had to be made.

1. **Disk I/O Bottlenecks:** AST parsing and indexing a massive enterprise repository creates thousands of node insertions and cross-reference queries in a matter of seconds. An on-disk database forces the operating system to perform frequent physical disk synchronization steps (`fsync`). Using an in-memory database keeps the entire data structure mapped inside RAM. This eliminates disk I/O bottlenecks entirely.

2. **Lifecycle Containment:** Sunder is designed around a strict zero-trust sandbox philosophy. Storing the AST on a physical host disk leaves behind structural footprints of the codebase in temporary folders. An in-memory database guarantees that when the CLI process exits, the entire indexed AST structure evaporates instantly from the host machine's memory registers, leaving zero artifacts behind.

## 5.3. Orchestration Layer Architecture

An *Evaluator-Optimizer* architecture along with a *Baseline* and *Adversarial* mode were chosen for the following reasons:

1. **Evaluator-Optimizer:** Traditional autonomous agents (like ReAct) can get trapped in endless loops of hallucinated commands when faced with complex execution errors. Sunder uses a strict Evaluator-Optimizer state machine to cleanly decouple test generation (the Coder) from error analysis (the Evaluator), ensuring a controlled execution flow.

2. **Context Window Protection:** When a sandbox execution fails, feeding the raw stack traces directly back to the Coder causes context window bloat and instruction confusion. The Evaluator node intercepts the Docker logs and synthesizes them into concise, actionable feedback (e.g., *"Mock the Postgres connection"*), preserving token economy for the next retry iteration.

3. **The Surface-Level Auth Hurdle:** If an AI attempts to generate chaotic fuzzing inputs immediately, the payloads are almost always rejected by surface-level middleware (e.g., missing API keys or invalid JWTs) before the testing can ever reach the target function's internal logic.

4. **Baseline State Seeding:** To solve this, Sunder enforces a two-step sequential architecture. It begins with the Baseline Phase, explicitly telling the LLM to write a "Happy Path" test that initializes mock database entities and fetches valid authentication tokens.

5. **Deep Adversarial Penetration:** Once the Baseline test exits cleanly, the extracted secrets and mock IDs are saved into the `EnvironmentState`. The Adversarial Phase injects this seeded state to seamlessly bypass basic access controls.