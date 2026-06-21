from sunder.schema import SunderAgentState
from sunder.execution.sandbox import SandboxExecutor

def executor_node(state: SunderAgentState) -> dict:
    """
    Runs the current test script inside the strictly isolated zero-trust sandbox.
    """
    executor = SandboxExecutor()
    
    # Execute the test using the profile set by the Client/TUI layer
    report = executor.run_test(
        target_path=state.context.target_node.file_path,
        image_tag=state.sandbox_config.custom_image,
        test_script=state.current_test_script,
        sandbox_profile=state.sandbox_config,
        language=state.context.target_node.language
    )
    
    # Update the state with the raw execution data and increment the retry counter
    return {
        "execution_report": report,
        "retry_count": state.retry_count + 1
    }