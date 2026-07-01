import os
import pytest
import tempfile
from sunder.execution.sandbox import SandboxExecutor
from sunder.schema import SandboxProfile, NetworkMode, LANGUAGE_RUN_COMMANDS

# ==========================================
# LANGUAGE INTEGRATION MAPS
# ==========================================

# Light, official images chosen to minimize disk footprint and pull times
LANGUAGE_IMAGE_MAP = {
    "python": "python:3.11-alpine",
    "javascript": "node:20-alpine",
    "typescript": "node:20-alpine",  
    "go": "golang:1.21-alpine",
    "java": "eclipse-temurin:17-alpine",  # Replaced deprecated openjdk
    "rust": "rust:1.75-alpine",
    "c": "gcc:13",                        # gcc does not have alpine variants
    "cpp": "gcc:13",                      # gcc does not have alpine variants
    "c-sharp": "mono:latest",             # mono does not have alpine variants
    "ruby": "ruby:3.2-alpine",
    "kotlin": "zenika/kotlin:latest",     # Replaced non-existent alpine tag
    "swift": "swift:5.9",                 # Replaced broken slim variant
    "php": "php:8.2-alpine",
    "dart": "dart:stable",
    "perl": "perl:5.38-slim",              # Fixed tag convention
    "lua": "alpine:3.19",            
    "r": "r-base:4.3.2",
    "elixir": "elixir:1.16-alpine",
    "erlang": "erlang:26-alpine",
    "haskell": "haskell:9.6-slim",
    "scala": "eclipse-temurin:17-alpine", # Replaced deprecated openjdk
    "bash": "alpine:3.19"
}

# Syntactically flawless structural payloads for each test framework/runner
LANGUAGE_VALID_SCRIPTS = {
    "python": "print('Sunder E2E Success')",
    "javascript": "console.log('Sunder E2E Success');",
    "typescript": "const msg: string = 'Sunder E2E Success'; console.log(msg);",
    "go": """package main
import "testing"
func TestExecution(t *testing.T) {
    t.Log("Sunder E2E Success")
}""",
    "java": """public class sunder_generated_testTest {
    public static void main(String[] args) {
        System.out.println("Sunder E2E Success");
    }
}""",
    "rust": "fn main() { println!(\"Sunder E2E Success\"); }",
    "c": '#include <stdio.h>\nint main() { printf("Sunder E2E Success\\n"); return 0; }',
    "cpp": '#include <iostream>\nint main() { std::cout << "Sunder E2E Success" << std::endl; return 0; }',
    "c-sharp": """using System;
class Program {
    static void Main() {
        Console.WriteLine("Sunder E2E Success");
    }
}""",
    "ruby": "puts 'Sunder E2E Success'",
    "kotlin": "fun main() { println(\"Sunder E2E Success\") }",
    "swift": "print(\"Sunder E2E Success\")",
    "php": "<?php echo 'Sunder E2E Success\\n'; ?>",
    "dart": """import 'package:test/test.dart';
void main() {
    test('E2E', () {
        assert(true);
    });
}""",
    "perl": "print \"Sunder E2E Success\\n\";",
    "lua": "print('Sunder E2E Success')",
    "r": "cat('Sunder E2E Success\\n')",
    "elixir": "IO.puts \"Sunder E2E Success\"",
    "erlang": """-module(sunder_generated_test_SUITE).
-export([test/0]).
test() -> io:format("Sunder E2E Success~n").""",
    "haskell": "main = putStrLn \"Sunder E2E Success\"",
    "scala": "@main def hello() = println(\"Sunder E2E Success\")",
    "bash": """#!/usr/bin/env bats
@test "Sunder Sandbox Pipeline Verification" {
  [ 0 -eq 0 ]
}"""
}

# ==========================================
# FIXTURES & CORE RUNNER
# ==========================================

@pytest.fixture(scope="module")
def shared_dummy_repo():
    """Creates a unified read-only mock enterprise codebase workspace."""
    with tempfile.TemporaryDirectory() as temp_dir:
        # Generate basic configuration descriptors to stabilize compilers (e.g., Go module resolution)
        with open(os.path.join(temp_dir, "go.mod"), "w") as f:
            f.write("module enterprise_app\ngo 1.21\n")
            
        src_dir = os.path.join(temp_dir, "src")
        os.makedirs(src_dir, exist_ok=True)
        with open(os.path.join(src_dir, "core.txt"), "w") as f:
            f.write("Enterprise Logic Core Place-holder")
            
        yield temp_dir


@pytest.mark.parametrize("language", LANGUAGE_RUN_COMMANDS.keys())
def test_language_execution_layer_e2e(shared_dummy_repo, language):
    """
    Performs a physical execution test for every language inside the sandbox.
    Verifies the Copy-on-Run mechanism, volume staging, and terminal exit evaluations.
    """
    image_tag = LANGUAGE_IMAGE_MAP.get(language)
    test_script = LANGUAGE_VALID_SCRIPTS.get(language)
    
    assert image_tag is not None, f"Missing image mapping definition for {language}"
    assert test_script is not None, f"Missing valid script syntax definition for {language}"
    
    # Configure an open bridge network and robust timeout to accommodate compiler building cold starts
    profile = SandboxProfile(
        network_mode=NetworkMode.BRIDGE,
        memory_limit="512m",
        cpu_quota=1.0,
        timeout_seconds=90,
        environment_vars={}
    )
    
    # Prerequisite Environment Preparation Actions for Bare Images
    if language == "lua":
        profile.environment_vars["BEFORE_EXECUTION"] = "apk add --no-cache lua5.3 && ln -s /usr/bin/lua5.3 /usr/bin/lua"
    elif language == "bash":
        profile.environment_vars["BEFORE_EXECUTION"] = "apk add --no-cache bats"
    elif language == "scala":
        profile.environment_vars["BEFORE_EXECUTION"] = "apk add --no-cache bash curl && curl -fL https://github.com/lampepfl/dotty/releases/download/3.3.1/scala3-3.3.1.tar.gz | tar -xzf - -C /usr/local --strip-components=1"
    elif language == "dart":
        profile.environment_vars["BEFORE_EXECUTION"] = "printf 'name: sunder_test\\nenvironment:\\n  sdk: ^3.0.0\\ndev_dependencies:\\n  test: any\\n' > pubspec.yaml && dart pub get"

    sandbox = SandboxExecutor()
    
    print(f"\\n[SUNDER E2E] Initializing live validation loop for language: {language.upper()} using {image_tag}")
    
    # Trigger active execution
    report = sandbox.run_test(
        target_path=shared_dummy_repo,
        image_tag=image_tag,
        test_script=test_script,
        sandbox_profile=profile,
        language=language
    )
    
    # ==========================================
    # ABSOLUTE PIPELINE ASSERTIONS
    # ==========================================
    assert report.timed_out is False, f"{language} execution hung up and exceeded the environment safety duration limit."
    assert report.oom_killed is False, f"{language} toolchain breached sandbox system memory resource boundary quotas."
    assert report.exit_code == 0, (
        f"Execution Layer Pipeline Fractured for language: {language.upper()}\\n"
        f"STDOUT Log Payload:\\n{report.stdout}\\n"
        f"STDERR Log Payload:\\n{report.stderr}"
    )
    
    print(f"[SUNDER E2E] Confirmed clean exit status for {language.upper()} in {report.duration_seconds} seconds.")