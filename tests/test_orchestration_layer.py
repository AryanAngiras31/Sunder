import pytest
import json
from unittest.mock import MagicMock, AsyncMock
from pydantic import SecretStr

from langchain_core.runnables import RunnableLambda
from langgraph.graph import END

from sunder.schema import (
    SunderAgentState, 
    EvaluationVerdict, 
    AgentMode, 
    AgentStatus,
    CoderOutput, 
    BaselineEvaluatorOutput, 
    AdversaryEvaluatorOutput,
    CodeNode,
    NodeType,
    BlastRadiusContext,
    SandboxProfile,
    ExecutionReport,
    EnvironmentState
)
from sunder.orchestration.orchestrator import SunderOrchestrator

# ==========================================
# FIXTURES
# ==========================================

@pytest.fixture
def dummy_code_node():
    return CodeNode(
        node_id="uuid-123",
        node_type=NodeType.FUNCTION,
        file_path="src/auth.py",
        symbol_name="verify_jwt",
        source_code="def verify_jwt(token):\n    pass",
        language="python"
    )

@pytest.fixture
def dummy_state(dummy_code_node):
    return SunderAgentState(
        mode=AgentMode.BASELINE,
        context=BlastRadiusContext(
            target_node=dummy_code_node,
            children=[],
            parents=[]
        ),
        sandbox_config=SandboxProfile(),
        env_state=EnvironmentState(),
        retry_count=0,
        max_retries=3
    )

@pytest.fixture
def mock_coder_llm():
    """Mocks a LangChain LLM returning a structured CoderOutput."""
    mock_llm = MagicMock()
    # We use RunnableLambda to allow the `prompt | structured_llm` pipe to work natively
    mock_llm.with_structured_output.return_value = RunnableLambda(
        lambda inputs: CoderOutput(test_script="print('Hello World')")
    )
    return mock_llm

@pytest.fixture
def mock_evaluator_llm():
    """Mocks a LangChain LLM. The exact return value will be configured per-test."""
    mock_llm = MagicMock()
    return mock_llm

@pytest.fixture
def orchestrator(mock_coder_llm, mock_evaluator_llm):
    """Provides a fully instantiated Orchestrator with mocked LLMs and Execution Layer."""
    orch = SunderOrchestrator(
        coder_llm=mock_coder_llm,
        evaluator_llm=mock_evaluator_llm,
        target_path="/fake/repo",
        image_tag="sunder-sandbox:latest"
    )
    # Mock the physical sandbox executor to prevent real Docker calls during orchestration testing
    orch.sandbox_executor = MagicMock()
    orch.sandbox_executor.run_test.return_value = ExecutionReport(
        exit_code=0, stdout="Success", stderr="", duration_seconds=1.5, oom_killed=False, timed_out=False
    )
    return orch


# ==========================================
# NODE TESTS (ASYNC)
# ==========================================

@pytest.mark.asyncio
async def test_baseline_coder_node(orchestrator, dummy_state):
    """Tests that the Baseline Coder returns the test script from the LLM."""
    result = await orchestrator.baseline_coder_node(dummy_state)
    
    assert "current_test_script" in result
    assert result["current_test_script"] == "print('Hello World')"


@pytest.mark.asyncio
async def test_adversary_coder_node_unmasks_secrets(orchestrator, dummy_state, mock_coder_llm):
    """Tests that the Adversary Coder properly unmasks SecretStr objects before sending to LLM."""
    dummy_state.mode = AgentMode.ADVERSARIAL
    dummy_state.env_state.auth_headers = {"Authorization": SecretStr("Bearer 12345")}
    
    # Capture the exact inputs passed to the LLM
    captured_inputs = {}
    async def capture_invoke(inputs):
        nonlocal captured_inputs
        captured_inputs = inputs
        return CoderOutput(test_script="def attack(): pass")
        
    mock_coder_llm.with_structured_output.return_value = RunnableLambda(capture_invoke)
    
    await orchestrator.adversary_coder_node(dummy_state)
    
    # Ensure the secret was unmasked in the prompt string
    assert "Bearer 12345" in captured_inputs["env_state"]
    assert "**********" not in captured_inputs["env_state"]


def test_executor_node(orchestrator, dummy_state):
    """Tests that the executor node invokes the sandbox and bumps the retry count."""
    dummy_state.retry_count = 1
    dummy_state.current_test_script = "print('Running')"
    
    result = orchestrator.executor_node(dummy_state)
    
    orchestrator.sandbox_executor.run_test.assert_called_once()
    assert "execution_report" in result
    assert result["execution_report"].exit_code == 0
    assert result["retry_count"] == 2  # Proves the retry counter was incremented


@pytest.mark.asyncio
async def test_evaluator_node_baseline_secure(orchestrator, dummy_state):
    """Tests extraction of environment secrets when Baseline test passes cleanly."""
    dummy_state.mode = AgentMode.BASELINE
    dummy_state.execution_report = ExecutionReport(
        exit_code=0, stdout="Token: abc", stderr="", duration_seconds=1.0, oom_killed=False, timed_out=False
    )
    
    # Mock LLM to simulate a successful Baseline extraction
    orchestrator.evaluator_llm.with_structured_output.return_value = RunnableLambda(
        lambda x: BaselineEvaluatorOutput(
            verdict=EvaluationVerdict.SYSTEM_SECURE,
            feedback="",
            extracted_auth_headers={"Authorization": "Bearer abc"},
            extracted_seeded_entities={"user_id": "999"}
        )
    )
    
    updates = await orchestrator.evaluator_node(dummy_state)
    
    assert updates["status"] == AgentStatus.COMPLETED
    assert updates["final_verdict"] == EvaluationVerdict.SYSTEM_SECURE
    assert "env_state" in updates
    
    # Verify the extracted strings were wrapped in Pydantic SecretStr for safety
    extracted_auth = updates["env_state"].auth_headers["Authorization"]
    assert isinstance(extracted_auth, SecretStr)
    assert extracted_auth.get_secret_value() == "Bearer abc"
    assert updates["env_state"].seeded_entities["user_id"] == "999"


@pytest.mark.asyncio
async def test_evaluator_node_syntax_error(orchestrator, dummy_state):
    """Tests that a Syntax Error keeps the agent pending and forwards feedback."""
    dummy_state.execution_report = ExecutionReport(
        exit_code=1, stdout="", stderr="SyntaxError", duration_seconds=1.0, oom_killed=False, timed_out=False
    )
    
    orchestrator.evaluator_llm.with_structured_output.return_value = RunnableLambda(
        lambda x: BaselineEvaluatorOutput(
            verdict=EvaluationVerdict.SYNTAX_ERROR,
            feedback="Fix the import statement on line 2."
        )
    )
    
    updates = await orchestrator.evaluator_node(dummy_state)
    
    assert updates["status"] == AgentStatus.PENDING
    assert updates["evaluator_feedback"] == "Fix the import statement on line 2."


@pytest.mark.asyncio
async def test_evaluator_node_max_retries_failure(orchestrator, dummy_state):
    """Tests that exceeding max retries forces the status to FAILED."""
    dummy_state.retry_count = 3
    dummy_state.max_retries = 3
    dummy_state.execution_report = ExecutionReport(
        exit_code=1, stdout="", stderr="Still broken", duration_seconds=1.0, oom_killed=False, timed_out=False
    )
    
    orchestrator.evaluator_llm.with_structured_output.return_value = RunnableLambda(
        lambda x: BaselineEvaluatorOutput(
            verdict=EvaluationVerdict.SYNTAX_ERROR, # Still failing
            feedback="Try again."
        )
    )
    
    updates = await orchestrator.evaluator_node(dummy_state)
    
    # The verdict is SYNTAX_ERROR, but because retries are exhausted, overarching status must be FAILED
    assert updates["status"] == AgentStatus.FAILED


# ==========================================
# ROUTING TESTS (SYNCHRONOUS)
# ==========================================

def test_route_start(orchestrator, dummy_state):
    dummy_state.mode = AgentMode.BASELINE
    assert orchestrator.route_start(dummy_state) == "baseline_coder"
    
    dummy_state.mode = AgentMode.ADVERSARIAL
    assert orchestrator.route_start(dummy_state) == "adversary_coder"


def test_route_evaluation_logic(orchestrator, dummy_state):
    dummy_state.retry_count = 1
    dummy_state.max_retries = 3
    
    # 1. Baseline Success -> END
    dummy_state.mode = AgentMode.BASELINE
    dummy_state.final_verdict = EvaluationVerdict.SYSTEM_SECURE
    assert orchestrator.route_evaluation(dummy_state) == END
    
    # 2. Adversarial Success (No Vuln Found) -> Keep looping (Adversary Coder)
    dummy_state.mode = AgentMode.ADVERSARIAL
    dummy_state.final_verdict = EvaluationVerdict.SYSTEM_SECURE
    assert orchestrator.route_evaluation(dummy_state) == "adversary_coder"
    
    # 3. Vulnerability Found -> Immediate END
    dummy_state.final_verdict = EvaluationVerdict.VULNERABILITY_FOUND
    assert orchestrator.route_evaluation(dummy_state) == END
    
    # 4. Syntax Error in Baseline -> Baseline Coder
    dummy_state.mode = AgentMode.BASELINE
    dummy_state.final_verdict = EvaluationVerdict.SYNTAX_ERROR
    assert orchestrator.route_evaluation(dummy_state) == "baseline_coder"


def test_route_evaluation_enforces_timeout(orchestrator, dummy_state):
    dummy_state.retry_count = 3
    dummy_state.max_retries = 3
    dummy_state.final_verdict = EvaluationVerdict.SYNTAX_ERROR
    
    # Normally a Syntax Error routes back to a coder, but max retries overrides it
    assert orchestrator.route_evaluation(dummy_state) == END