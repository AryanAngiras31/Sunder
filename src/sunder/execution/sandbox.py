import os
import time
import tempfile
import docker
from docker.errors import APIError
from sunder.schema import SandboxProfile, ExecutionReport, LANGUAGE_EXTENSION_MAP

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

        # Create a temporary directory on the host to hold the volatile test script
        with tempfile.TemporaryDirectory() as temp_dir:
            test_file_path = os.path.join(temp_dir, file_name)
            with open(test_file_path, "w") as f:
                f.write(test_script)

            # Define strict volume mounts
            volumes = {
                # Mount the enterprise codebase as purely read-only
                os.path.abspath(target_path): {
                    'bind': '/app', 
                    'mode': 'ro'
                },
                # Mount the temporary test script directory
                os.path.abspath(temp_dir): {
                    'bind': '/sunder_test', 
                    'mode': 'rw'
                }
            }

            start_time = time.time()
            container = None
            timed_out = False

            # Inject env variables to allow the tests to import code from the ro user code
            env_vars = sandbox_profile.environment_vars.copy()
            env_vars["PYTHONPATH"] = "/app"
            env_vars["PYTHONDONTWRITEBYTECODE"] = "1"
            
            try:
                # Start the container in detached mode so we can manually enforce timeouts
                container = self.client.containers.run(
                    image=image_tag,
                    volumes=volumes,
                    working_dir="/app",
                    network_mode=sandbox_profile.network_mode.value,
                    mem_limit=sandbox_profile.memory_limit,
                    cpu_quota=int(sandbox_profile.cpu_quota * 100000),   # Convert fractional CPU to Docker's cpu_quota (100000 = 1 core)
                    environment=env_vars,
                    detach=True
                )

                # Polling loop to enforce the timeout_seconds constraint
                while container.status in ['created', 'running']:
                    if time.time() - start_time > sandbox_profile.timeout_seconds:
                        container.kill()
                        timed_out = True
                        break
                    time.sleep(0.5)
                    container.reload() # Refresh container status from daemon

                # Wait for container to finalize and extract the exit code
                result = container.wait()
                exit_code = result.get('StatusCode', 137 if timed_out else 1)

                # Extract telemetry
                stdout = container.logs(stdout=True, stderr=False).decode('utf-8', errors='replace')
                stderr = container.logs(stdout=False, stderr=True).decode('utf-8', errors='replace')
                
                # Check for Out-Of-Memory kills
                container_info = self.client.api.inspect_container(container.id)
                oom_killed = container_info['State'].get('OOMKilled', False)
                
                duration = round(time.time() - start_time, 2)

                return ExecutionReport(
                    exit_code=exit_code,
                    stdout=stdout,
                    stderr=stderr,
                    duration_seconds=duration,
                    oom_killed=oom_killed,
                    timed_out=timed_out
                )

            except APIError as e:
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
                    except APIError:
                        pass