from sunder.schema import SunderAgentState, CoderOutput
from sunder.orchestration.prompts import BASELINE_CODER_PROMPT

def make_baseline_coder_node(coder_llm):
    """Factory that injects the BYOK LLM and returns the LangGraph node."""
    
    # 1. Initialize the strict output schema once
    structured_llm = coder_llm.with_structured_output(CoderOutput)
    chain = BASELINE_CODER_PROMPT | structured_llm

    # 2. Define the actual node function
    async def node(state: SunderAgentState) -> dict:
        target = state.context.target_node
        
        response: CoderOutput = await chain.ainvoke({
            "symbol_name": target.symbol_name,
            "file_path": target.file_path,
            "language": target.language,
            "source_code": target.source_code,
            "previous_test": state.current_test_script if state.retry_count > 0 else "None. This is the first attempt.",
            "feedback": state.evaluator_feedback if state.retry_count > 0 else "None. This is the first attempt."
        })
        
        return {"current_test_script": response.test_script}
        
    return node