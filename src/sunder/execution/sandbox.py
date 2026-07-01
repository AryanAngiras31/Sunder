import os
import time
import tempfile
import logging
import requests
import shlex
import docker
from docker.types import Mount
from docker.errors import APIError
from sunder.schema import SandboxProfile, ExecutionReport, LANGUAGE_EXTENSION_MAP, LANGUAGE_RUN_COMMANDS, SKIP_FOLDERS

# Initialize standard Python logger
logger = logging.getLogger(__name__)

class SandboxExecutor:
    def __init__(self):
        self.client = docker.from_env()

    def run_test(
        self, 
        target_path: str, 
        image_tag: str, 
        test_script: str, 
        sandbox_profile: SandboxProfile,
        language: str
    ) -> ExecutionReport:
        """
        Executes the AI-generated test script inside the zero-trust container.
        """
        # Resolve the correct test file suffix
        file_suffix = LANGUAGE_EXTENSION_MAP.get(language.lower(), ".txt")
        file_name = f"sunder_generated_test{file_suffix}"
        
        logger.debug(f"Preparing sandbox execution for {language} target...")

        # Create a temporary directory on the host to hold the volatile test script
        with tempfile.TemporaryDirectory() as temp_dir:
            test_file_path = os.path.join(temp_dir, file_name)
            with open(test_file_path, "w") as f:
                f.write(test_script)

            # Define strict volume mounts
            mounts = [
                Mount(
                    target='/ro_app',
                    source=os.path.abspath(target_path),
                    type='bind',
                    read_only=True
                ),
                Mount(
                    target='/sunder_test',
                    source=os.path.abspath(temp_dir),
                    type='bind',
                    read_only=True
                )
            ]

            # Dynamically merge user-defined ignores with Sunder's hardcoded skips
            dynamic_skips = set(SKIP_FOLDERS)
            gitignore_path = os.path.join(target_path, ".gitignore")
            
            if os.path.exists(gitignore_path):
                with open(gitignore_path, "r") as ig_file:
                    for line in ig_file:
                        line = line.strip()
                        
                        # Skip empty lines, comments, and negations 
                        if not line or line.startswith("#") or line.startswith("!"):
                            continue
                        
                        # Translate Root Anchors
                        if line.startswith('/'):
                            line = f".{line}"
                            
                        # 3. Strip Trailing Slashes
                        line = line.rstrip('/')
                        
                        dynamic_skips.add(line)

            # We use shlex.quote() to safely wrap the wildcard patterns (e.g. *.log, data/*).
            # This prevents adversarial command injection if a bad actor poisons the .gitignore.
            tar_excludes = " ".join([f"--exclude={shlex.quote(folder)}" for folder in dynamic_skips])
            
            # Fetch the execution command for the target language
            run_cmd = LANGUAGE_RUN_COMMANDS.get(language.lower(), f"cat {file_name}")
            
            pre_req_setup = sandbox_profile.environment_vars.get("BEFORE_EXECUTION", "")
            setup_prefix = f"{pre_req_setup} && " if pre_req_setup else ""

            # The UNIX Tar-Pipe
            # 1. 'tar -c' creates a stream of /ro_app, skipping massive folders (node_modules, .git, etc.)
            # 2. 'tar -x' instantly extracts physical files into the writable /app directory
            # 3. Preserves container-native dependencies built via the Dockerfile
            shell_command = (
                f"sh -c '"
                f"{setup_prefix}"
                f"tar -c -C /ro_app {tar_excludes} . | tar -x -C /app && "
                f"cp /sunder_test/{file_name} /app/ && "
                f"{run_cmd}'"
            )

            start_time = time.time()
            container = None
            timed_out = False

            try:
                logger.debug(f"Starting container with image {image_tag}")
                # Start the container in detached mode so we can manually enforce timeouts
                container = self.client.containers.run(
                    image=image_tag,
                    mounts=mounts,
                    working_dir="/app",
                    command=shell_command,
                    network_mode=sandbox_profile.network_mode.value,
                    mem_limit=sandbox_profile.memory_limit,
                    cpu_quota=int(sandbox_profile.cpu_quota * 100000),   # Convert fractional CPU to Docker's cpu_quota (100000 = 1 core)
                    environment=sandbox_profile.environment_vars,
                    detach=True
                )

                # Get results from the run while enforcing the timeout
                try:
                    result = container.wait(timeout=sandbox_profile.timeout_seconds)
                    exit_code = result.get('StatusCode', 1) 

                except (requests.exceptions.ReadTimeout, requests.exceptions.ConnectionError) as e:
                    # When a socket connection to a container is closed, docker does not know if it was due to a timeout or another reason 
                    # This is why it allows requests exceptions to bleed through.
                    # We check the elapsed time to verify it was a true timeout and not a daemon crash.
                    elapsed = time.time() - start_time
                    if elapsed >= sandbox_profile.timeout_seconds - 1:  # Use a 1 second buffer to take into accound premature timeout 
                        logger.warning(f"Sandbox execution timed out after {sandbox_profile.timeout_seconds}s. Killing container.")
                        try:
                            container.kill()
                        except APIError:
                            pass # Container might have already died 
                        timed_out = True
                        exit_code = 137
                    else:
                        raise APIError(f"Connection to Docker daemon dropped unexpectedly: {e}")

                # Extract telemetry
                stdout = container.logs(stdout=True, stderr=False).decode('utf-8', errors='replace')
                stderr = container.logs(stdout=False, stderr=True).decode('utf-8', errors='replace')
                
                # Check for Out-Of-Memory kills
                container_info = self.client.api.inspect_container(container.id)
                oom_killed = container_info['State'].get('OOMKilled', False)
                
                duration = round(time.time() - start_time, 2)

                # Log sandbox metrics using local variables
                if oom_killed:
                    logger.warning("Sandbox execution was OOM killed")
                elif not timed_out:
                    logger.debug(f"Sandbox execution completed cleanly with exit code {exit_code} in {duration}s")

                return ExecutionReport(
                    exit_code=exit_code,
                    stdout=stdout,
                    stderr=stderr,
                    duration_seconds=duration,
                    oom_killed=oom_killed,
                    timed_out=timed_out
                )

            except APIError as e:
                logger.error(f"Host-Level Docker API Error: {str(e)}")
                return ExecutionReport(
                    exit_code=-1,
                    stdout="",
                    stderr=f"Host-Level Docker API Error: {str(e)}",
                    duration_seconds=0.0,
                    oom_killed=False,
                    timed_out=False
                )
            
            finally:
                # Guarantee the container is destroyed regardless of errors
                if container:
                    try:
                        container.remove(force=True)
                    except APIError as e:
                        logger.debug(f"Failed to silently remove container {container.id}: {e}")