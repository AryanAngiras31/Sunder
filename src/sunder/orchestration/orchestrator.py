from langgraph.graph import StateGraph, END

import json
from pydantic import SecretStr

from sunder.schema import (
    SunderAgentState, 
    EvaluationVerdict, 
    AgentMode, 
    AgentStatus,
    CoderOutput, 
    BaselineEvaluatorOutput, 
    AdversaryEvaluatorOutput
)
from sunder.orchestration.prompts import (
    BASELINE_CODER_PROMPT, 
    ADVERSARY_CODER_PROMPT,
    BASELINE_EVALUATOR_PROMPT, 
    ADVERSARY_EVALUATOR_PROMPT
)
from sunder.execution.sandbox import SandboxExecutor


class SunderOrchestrator:
    """
    Object-Oriented LangGraph Orchestrator.
    Persists BYOK models and static infrastructure variables at the instance level.
    """
    def __init__(self, coder_llm, evaluator_llm, target_path: str, image_tag: str):
        self.coder_llm = coder_llm
        self.evaluator_llm = evaluator_llm
        self.target_path = target_path
        self.image_tag = image_tag
        self.sandbox_executor = SandboxExecutor()

    # ==========================================
    # NODES
    # ==========================================

    async def baseline_coder_node(self, state: SunderAgentState) -> dict:
        target = state.context.target_node
        
        structured_llm = self.coder_llm.with_structured_output(CoderOutput)
        chain = BASELINE_CODER_PROMPT | structured_llm
        
        response: CoderOutput = await chain.ainvoke({
            "symbol_name": target.symbol_name,
            "file_path": target.file_path,
            "language": target.language,
            "source_code": target.source_code,
            "previous_test": state.current_test_script if state.retry_count > 0 else "None. This is the first attempt.",
            "feedback": state.evaluator_feedback if state.retry_count > 0 else "None. This is the first attempt."
        })

        return {"current_test_script": response.test_script}


    async def adversary_coder_node(self, state: SunderAgentState) -> dict:
        target = state.context.target_node

        # Explicitly unmask secrets for the LLM prompt
        env = state.env_state
        exposed_env_dict = {}
        if env:
            exposed_env_dict = {
                "auth_headers": {k: v.get_secret_value() for k, v in env.auth_headers.items()},
                "cookies": {k: v.get_secret_value() for k, v in env.cookies.items()},
                "mock_credentials": {k: v.get_secret_value() for k, v in env.mock_credentials.items()},
                "seeded_entities": env.seeded_entities,
                "dynamic_endpoints": env.dynamic_endpoints,
                "ephemeral_files": env.ephemeral_files
            }

        structured_llm = self.coder_llm.with_structured_output(CoderOutput)
        chain = ADVERSARY_CODER_PROMPT | structured_llm
        
        response: CoderOutput = await chain.ainvoke({
            "symbol_name": target.symbol_name,
            "file_path": target.file_path,
            "language": target.language,
            "source_code": target.source_code,
            "env_state": json.dumps(exposed_env_dict, indent=2) if exposed_env_dict else "None available.",
            "previous_test": state.current_test_script if state.retry_count > 0 else "None. This is the first attempt.",
            "feedback": state.evaluator_feedback if state.retry_count > 0 else "None. This is the first attack vector attempt."
        })

        return {"current_test_script": response.test_script}


    def executor_node(self, state: SunderAgentState) -> dict:
        # Run the latest test script in the sandbox
        report = self.sandbox_executor.run_test(
            target_path=self.target_path,
            image_tag=self.image_tag,
            test_script=state.current_test_script,
            sandbox_profile=state.sandbox_config,
            language=state.context.target_node.language
        )

        return {
            "execution_report": report,
            "retry_count": state.retry_count + 1
        }


    async def evaluator_node(self, state: SunderAgentState) -> dict:
        report = state.execution_report
        
        # Dynamically select Prompt and Strict Schema based on Mode
        if state.mode == AgentMode.BASELINE:
            prompt = BASELINE_EVALUATOR_PROMPT
            structured_llm = self.evaluator_llm.with_structured_output(BaselineEvaluatorOutput)
        else:
            prompt = ADVERSARY_EVALUATOR_PROMPT
            structured_llm = self.evaluator_llm.with_structured_output(AdversaryEvaluatorOutput)
            
        chain = prompt | structured_llm
        eval_result = await chain.ainvoke({
            "source_code": state.context.target_node.source_code,
            "current_test_script": state.current_test_script,
            "exit_code": report.exit_code,
            "stdout": report.stdout,
            "stderr": report.stderr
        })
        
        # Determine overarching agent status based on the verdict
        new_status = AgentStatus.PENDING
        if eval_result.verdict == EvaluationVerdict.VULNERABILITY_FOUND:
            new_status = AgentStatus.COMPLETED
        else:
            if state.mode == AgentMode.BASELINE and eval_result.verdict == EvaluationVerdict.SYSTEM_SECURE:
                new_status = AgentStatus.COMPLETED

        # Determine if the coding agent exhausted retries without success
        if new_status == AgentStatus.PENDING and state.retry_count >= state.max_retries:
            new_status = AgentStatus.FAILED

        updates = {
            "evaluator_feedback": eval_result.feedback,
            "final_verdict": eval_result.verdict,
            "status": new_status
        }
        
        # Safely extract secrets if Baseline passed
        if state.mode == AgentMode.BASELINE and eval_result.verdict == EvaluationVerdict.SYSTEM_SECURE:
            # Create a detached clone of the EnvironmentState
            current_env = state.env_state.model_copy(deep=True)
            
            # Wrap sensitive strings in SecretStr before updating the environment
            secure_auth = {k: SecretStr(v) for k, v in eval_result.extracted_auth_headers.items()}
            current_env.auth_headers.update(secure_auth)
            
            secure_cookies = {k: SecretStr(v) for k, v in eval_result.extracted_cookies.items()}
            current_env.cookies.update(secure_cookies)
            
            secure_creds = {k: SecretStr(v) for k, v in eval_result.extracted_mock_credentials.items()}
            current_env.mock_credentials.update(secure_creds)
            
            # Merge standard strings and lists
            current_env.seeded_entities.update(eval_result.extracted_seeded_entities)
            current_env.dynamic_endpoints.update(eval_result.extracted_dynamic_endpoints)
            current_env.ephemeral_files.extend(eval_result.extracted_ephemeral_files)
            
            updates["env_state"] = current_env

        return updates


    # ==========================================
    # ROUTING LOGIC
    # ==========================================

    def route_start(self, state: SunderAgentState) -> str:
        if state.mode == AgentMode.BASELINE:
            return "baseline_coder"
        return "adversary_coder"

    def route_evaluation(self, state: SunderAgentState) -> str:
        # Check timeout limit dynamically from state
        if state.retry_count >= state.max_retries:
            return END
            
        verdict = state.final_verdict
        mode = state.mode
        
        # Always fix syntax error in the test
        if verdict == EvaluationVerdict.SYNTAX_ERROR:
            return "baseline_coder" if mode == AgentMode.BASELINE else "adversary_coder"
            
        # Always end when a vulnerability is found regardless of the mode
        if verdict == EvaluationVerdict.VULNERABILITY_FOUND:
            return END
        
        # If system is secure and mode is baseline then success
        if verdict == EvaluationVerdict.SYSTEM_SECURE:
            if mode == AgentMode.BASELINE:
                return END
            else:
                return "adversary_coder"


    # ==========================================
    # GRAPH COMPILATION
    # ==========================================

    def build_graph(self):
        workflow = StateGraph(SunderAgentState)
        
        # Add methods as nodes
        workflow.add_node("baseline_coder", self.baseline_coder_node)
        workflow.add_node("adversary_coder", self.adversary_coder_node)
        workflow.add_node("executor", self.executor_node)
        workflow.add_node("evaluator", self.evaluator_node)
        
        # Start based on the mode
        workflow.set_conditional_entry_point(self.route_start)
        
        workflow.add_edge("baseline_coder", "executor")
        workflow.add_edge("adversary_coder", "executor")
        workflow.add_edge("executor", "evaluator")
        
        workflow.add_conditional_edges("evaluator", self.route_evaluation)
        
        return workflow.compile()