from sunder.schema import (
    SunderAgentState, 
    EvaluationVerdict, 
    AgentMode, 
    AgentStatus,
    BaselineEvaluatorOutput, 
    AdversaryEvaluatorOutput
)
from sunder.orchestration.prompts import BASELINE_EVALUATOR_PROMPT, ADVERSARY_EVALUATOR_PROMPT

def make_evaluator_node(evaluator_llm):
    
    async def node(state: SunderAgentState) -> dict:
        report = state.execution_report
        
        # Select Strict Schema and Prompt based on Mode
        if state.mode == AgentMode.BASELINE:
            prompt = BASELINE_EVALUATOR_PROMPT
            structured_llm = evaluator_llm.with_structured_output(BaselineEvaluatorOutput)
        else:
            prompt = ADVERSARY_EVALUATOR_PROMPT
            structured_llm = evaluator_llm.with_structured_output(AdversaryEvaluatorOutput)
            
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
            if state.mode.value == "baseline" and  eval_result.verdict == EvaluationVerdict.SYSTEM_SECURE:
                new_status = AgentStatus.COMPLETED

        updates = {
            "evaluator_feedback": eval_result.feedback,
            "final_verdict": eval_result.verdict,
            "status": new_status
        }
        
        # Safely extract secrets if Baseline passed
        if state.mode == AgentMode.BASELINE and eval_result.verdict == EvaluationVerdict.SYSTEM_SECURE:
            current_env = state.env_state
            current_env.auth_headers.update(eval_result.extracted_auth_headers)
            current_env.seeded_entities.update(eval_result.extracted_seeded_entities)
            updates["env_state"] = current_env

        return updates
        
    return node