from sunder.schema import SunderAgentState
from sunder.execution.sandbox import SandboxExecutor

def make_executor_node(target_path: str, image_tag: str):
    """Factory that injects static infrastructure paths into the node."""
    
    def node(state: SunderAgentState) -> dict:
        executor = SandboxExecutor()
        
        report = executor.run_test(
            target_path=target_path,
            image_tag=image_tag,
            test_script=state.current_test_script,
            sandbox_profile=state.sandbox_config,
            language=state.context.target_node.language
        )
        
        return {
            "execution_report": report,
            "retry_count": state.retry_count + 1
        }
        
    return node