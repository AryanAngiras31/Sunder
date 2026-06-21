from langgraph.graph import StateGraph, END
from sunder.schema import SunderAgentState, AgentMode, EvaluationVerdict

from sunder.orchestration.nodes.baseline_coder import baseline_coder_node
from sunder.orchestration.nodes.adversary_coder import adversary_coder_node
from sunder.orchestration.nodes.executor import executor_node
from sunder.orchestration.nodes.evaluator import evaluator_node

def route_start(state: SunderAgentState) -> str:
    """Routes the initial execution based on the chosen mode."""
    if state.mode == AgentMode.BASELINE:
        return "baseline_coder"
    return "adversary_coder"


def route_evaluation(state: SunderAgentState) -> str:
    """
    The Decision Engine. Evaluates the verdict and current retry count 
    to route back to a coder or terminate the graph.
    """
    # Hard Timeout / Limit Reached
    if state.retry_count >= state.max_retries:
        return END
        
    verdict = state.final_verdict
    mode = state.mode
    
    # LLM hallucinated or wrote bad code -> retry
    if verdict == EvaluationVerdict.SYNTAX_ERROR:
        return "baseline_coder" if mode == AgentMode.BASELINE else "adversary_coder"
        
    # Hard crash or assertion tripped -> Always terminate and report
    if verdict == EvaluationVerdict.VULNERABILITY_FOUND:
        return END
        
    # SYSTEM_SECURE: Handled gracefully
    if verdict == EvaluationVerdict.SYSTEM_SECURE:
        if mode == AgentMode.BASELINE:
            # Baseline succeeded. The state is seeded.
            return END
        else:
            # Adversary failed to break the system. Route back to try a new attack vector.
            return "adversary_coder"


def build_sunder_graph():
    """Assembles and compiles the Sunder Orchestration state machine."""
    workflow = StateGraph(SunderAgentState)
    
    # Add the 4 core nodes
    workflow.add_node("baseline_coder", baseline_coder_node)
    workflow.add_node("adversary_coder", adversary_coder_node)
    workflow.add_node("executor", executor_node)
    workflow.add_node("evaluator", evaluator_node)
    
    # Set the entry point
    workflow.set_conditional_entry_point(route_start)
    
    # Set standard sequential edges
    workflow.add_edge("baseline_coder", "executor")
    workflow.add_edge("adversary_coder", "executor")
    workflow.add_edge("executor", "evaluator")
    
    # Set the conditional routing edge from the Evaluator
    workflow.add_conditional_edges("evaluator", route_evaluation)
    
    return workflow.compile()