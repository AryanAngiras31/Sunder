import os
import pytest
from pathlib import Path
from sunder.execution.bootstrapper import Bootstrapper
from sunder.execution.sandbox import SandboxExecutor
from sunder.schema import SandboxProfile, NetworkMode

# --- FIXTURES ---

@pytest.fixture
def dummy_target_repo(tmp_path):
    """Creates a temporary directory simulating a user's repository with a .sunder/Dockerfile."""
    target_dir = tmp_path / "mock_repo"
    target_dir.mkdir()
    
    # Create mock enterprise code to test cross-mount importing
    src_dir = target_dir / "src"
    src_dir.mkdir()
    math_logic = src_dir / "calculator.py"
    math_logic.write_text("def add(a, b):\n    return a + b\n")
    
    sunder_dir = target_dir / ".sunder"
    sunder_dir.mkdir()
    
    dockerfile = sunder_dir / "Dockerfile"
    # A lightweight Alpine Python image for fast testing
    dockerfile.write_text(
        "FROM python:3.11-alpine\n"
    )
    
    return str(target_dir)

@pytest.fixture
def sandbox_profile():
    """Provides a default strict sandbox profile."""
    return SandboxProfile(
        network_mode=NetworkMode.NONE,
        memory_limit="128m",
        cpu_quota=1.0,
        timeout_seconds=3, # Keep tests fast
        environment_vars={"TEST_ENV": "active"}
    )

# --- BOOTSTRAPPER TESTS ---

def test_bootstrapper_builds_image(dummy_target_repo):
    bootstrapper = Bootstrapper()
    
    # Should build the image and return a tag like 'sunder-sandbox:abcdef123456'
    image_tag = bootstrapper.ensure_environment(dummy_target_repo)
    
    assert image_tag.startswith("sunder-sandbox:")
    assert len(image_tag.split(":")[1]) == 12

def test_bootstrapper_missing_dockerfile(tmp_path):
    bootstrapper = Bootstrapper()
    empty_repo = str(tmp_path / "empty_repo")
    os.makedirs(empty_repo)
    
    with pytest.raises(FileNotFoundError, match="Strict Enforcement Failed"):
        bootstrapper.ensure_environment(empty_repo)

# --- SANDBOX TESTS ---

def test_sandbox_clean_execution(dummy_target_repo, sandbox_profile):
    bootstrapper = Bootstrapper()
    image_tag = bootstrapper.ensure_environment(dummy_target_repo)
    
    sandbox = SandboxExecutor()
    test_script = "import os\nprint('Execution successful!')\nprint(os.environ.get('TEST_ENV'))"
    
    report = sandbox.run_test(
        target_path=dummy_target_repo,
        image_tag=image_tag,
        test_script=test_script,
        sandbox_profile=sandbox_profile,
        language="python"
    )
    
    assert report.exit_code == 0
    assert "Execution successful!" in report.stdout
    assert "active" in report.stdout # Checks environment variable injection
    assert report.timed_out is False
    assert report.oom_killed is False

def test_sandbox_cross_mount_import(dummy_target_repo, sandbox_profile):
    """Tests if the isolated test script can successfully import from the read-only enterprise mount."""
    bootstrapper = Bootstrapper()
    image_tag = bootstrapper.ensure_environment(dummy_target_repo)
    
    sandbox = SandboxExecutor()
    
    # This script lives in /sunder_test but imports from /app/src
    test_script = (
        "from src.calculator import add\n"
        "result = add(10, 5)\n"
        "print(f'Sunder Calculation: {result}')\n"
    )
    
    report = sandbox.run_test(
        target_path=dummy_target_repo,
        image_tag=image_tag,
        test_script=test_script,
        sandbox_profile=sandbox_profile,
        language="python"
    )
    
    assert report.exit_code == 0, f"Execution failed. Stderr: {report.stderr}"
    assert "Sunder Calculation: 15" in report.stdout
    assert report.timed_out is False

def test_sandbox_timeout_enforcement(dummy_target_repo, sandbox_profile):
    bootstrapper = Bootstrapper()
    image_tag = bootstrapper.ensure_environment(dummy_target_repo)
    
    sandbox = SandboxExecutor()
    # An infinite loop to trigger the timeout
    test_script = "while True:\n    pass"
    
    report = sandbox.run_test(
        target_path=dummy_target_repo,
        image_tag=image_tag,
        test_script=test_script,
        sandbox_profile=sandbox_profile,
        language="python"
    )
    
    assert report.exit_code == 137  # Standard Docker exit code for SIGKILL
    assert report.timed_out is True
    assert report.duration_seconds >= sandbox_profile.timeout_seconds

def test_sandbox_syntax_error(dummy_target_repo, sandbox_profile):
    bootstrapper = Bootstrapper()
    image_tag = bootstrapper.ensure_environment(dummy_target_repo)
    
    sandbox = SandboxExecutor()
    test_script = "def invalid_python_syntax(:\n    pass"
    
    report = sandbox.run_test(
        target_path=dummy_target_repo,
        image_tag=image_tag,
        test_script=test_script,
        sandbox_profile=sandbox_profile,
        language="python"
    )
    
    assert report.exit_code != 0
    assert "SyntaxError" in report.stderr

def test_sandbox_gitignore_tar_pipe_exclusion(dummy_target_repo, sandbox_profile):
    """
    Tests that the Tar-Pipe correctly parses .gitignore, translates Git syntax 
    to tar exclusions, and safely escapes shell injections.
    """
    target_path = Path(dummy_target_repo)
    
    # Setup the edge-case .gitignore
    gitignore_path = target_path / ".gitignore"
    gitignore_path.write_text(
        "# This is a comment and should be ignored\n"
        "heavy_dataset/\n"               # Tests trailing slash stripping
        "/root_cache\n"                  # Tests root anchor translation
        "*.log\n"                        # Tests wildcard evaluation
        "!important.log\n"               # Tests negation skipping (unsupported by tar)
        "malicious_dir'; rm -rf /; '\n"  # Tests shlex shell escaping
    )
    
    # Generate the physical files and directories
    (target_path / "heavy_dataset").mkdir()
    (target_path / "heavy_dataset" / "data.bin").write_text("101010")
    
    (target_path / "root_cache").mkdir()
    (target_path / "root_cache" / "cache.bin").write_text("101010")
    
    (target_path / "debug.log").write_text("crash trace")
    (target_path / "valid_file.txt").write_text("keep me")

    # Build image and run sandbox
    bootstrapper = Bootstrapper()
    image_tag = bootstrapper.ensure_environment(dummy_target_repo)
    
    sandbox = SandboxExecutor()
    
    # The AI test script will traverse the container's /app directory and dump all file names
    test_script = (
        "import os\n"
        "found = set()\n"
        "for root, dirs, files in os.walk('/app'):\n"
        "    for name in dirs + files:\n"
        "        found.add(name)\n"
        "print(f'FOUND: {found}')\n"
    )
    
    report = sandbox.run_test(
        target_path=dummy_target_repo,
        image_tag=image_tag,
        test_script=test_script,
        sandbox_profile=sandbox_profile,
        language="python"
    )
    
    # Assert Pipeline Integrity
    assert report.exit_code == 0, f"Tar-Pipe crashed. Stderr: {report.stderr}"
    stdout = report.stdout
    
    # Assert File Exclusions
    assert "valid_file.txt" in stdout, "Tar-Pipe failed to copy valid host files."
    assert "heavy_dataset" not in stdout, "Tar-Pipe failed to parse and exclude trailing-slash directories."
    assert "root_cache" not in stdout, "Tar-Pipe failed to translate and exclude root-anchored directories."
    assert "debug.log" not in stdout, "Tar-Pipe failed to evaluate glob wildcards."
    
    # If the shell injection payload had broken out of shlex.quote, the tar command would 
    # have shattered, returning exit_code > 0 and skipping the Python script entire