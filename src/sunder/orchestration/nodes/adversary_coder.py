from sunder.schema import SunderAgentState, CoderOutput
from sunder.orchestration.prompts import ADVERSARY_CODER_PROMPT

def make_adversary_coder_node(coder_llm):
    structured_llm = coder_llm.with_structured_output(CoderOutput)
    chain = ADVERSARY_CODER_PROMPT | structured_llm

    async def node(state: SunderAgentState) -> dict:
        target = state.context.target_node
        env = state.env_state
        
        response: CoderOutput = await chain.ainvoke({
            "symbol_name": target.symbol_name,
            "file_path": target.file_path,
            "language": target.language,
            "source_code": target.source_code,
            "env_state": env.model_dump_json(indent=2) if env else "None available.",
            "previous_test": state.current_test_script if state.retry_count > 0 else "None. This is the first attempt.",
            "feedback": state.evaluator_feedback if state.retry_count > 0 else "None. This is the first attack vector attempt."
        })
        
        return {"current_test_script": response.test_script}
        
    return node