from langgraph.graph import StateGraph, END
from sunder.schema import SunderAgentState, AgentMode, EvaluationVerdict

# Import node factories
from sunder.orchestration.nodes.baseline_coder import make_baseline_coder_node
from sunder.orchestration.nodes.adversary_coder import make_adversary_coder_node
from sunder.orchestration.nodes.executor import make_executor_node
from sunder.orchestration.nodes.evaluator import make_evaluator_node

class SunderOrchestrator:
    def __init__(self, coder_llm, evaluator_llm, target_path: str, image_tag: str):
        self.coder_llm = coder_llm
        self.evaluator_llm = evaluator_llm
        self.target_path = target_path
        self.image_tag = image_tag

    # ==========================================
    # ROUTING LOGIC
    # ==========================================

    def route_start(self, state: SunderAgentState) -> str:
        if state.mode == AgentMode.BASELINE:
            return "baseline_coder"
        return "adversary_coder"

    def route_evaluation(self, state: SunderAgentState) -> str:
        if state.retry_count >= state.max_retries:
            return END
            
        verdict = state.final_verdict
        mode = state.mode
        
        if verdict == EvaluationVerdict.SYNTAX_ERROR:
            return "baseline_coder" if mode == AgentMode.BASELINE else "adversary_coder"
            
        if verdict == EvaluationVerdict.VULNERABILITY_FOUND:
            return END
            
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
        
        # Dynamically create nodes using factories, injecting the class properties
        workflow.add_node("baseline_coder", make_baseline_coder_node(self.coder_llm))
        workflow.add_node("adversary_coder", make_adversary_coder_node(self.coder_llm))
        workflow.add_node("executor", make_executor_node(self.target_path, self.image_tag))
        workflow.add_node("evaluator", make_evaluator_node(self.evaluator_llm))
        
        workflow.set_conditional_entry_point(self.route_start)
        
        workflow.add_edge("baseline_coder", "executor")
        workflow.add_edge("adversary_coder", "executor")
        workflow.add_edge("executor", "evaluator")
        
        workflow.add_conditional_edges("evaluator", self.route_evaluation)
        
        return workflow.compile()