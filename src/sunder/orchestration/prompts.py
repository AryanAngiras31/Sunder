from langchain_core.prompts import ChatPromptTemplate

# ==========================================
# BASELINE CODER PROMPT
# ==========================================
BASELINE_CODER_PROMPT = ChatPromptTemplate.from_messages([
    (
        "system", 
        "You are an expert security engineer. Your objective is to write a test suite of"
        "functional 'Happy Path' unit tests for the provided target function.\n\n"
        "REQUIREMENTS:\n"
        "1. Prime any required mock database state.\n"
        "2. Fetch or mock valid authentication tokens (e.g., JWTs) if required to execute the target.\n"
        "3. Print any dynamically generated mock IDs or credentials to standard output so they can be captured.\n"
        "4. Do NOT write adversarial payloads. This test MUST pass cleanly (Exit Code 0).\n"
        "5. Output ONLY the raw test script code inside a markdown code block."
    ),
    (
        "user", 
        "TARGET FUNCTION: {symbol_name}\n"
        "FILE PATH: {file_path}\n"
        "LANGUAGE: {language}\n\n"
        "TARGET SOURCE CODE:\n```\n{source_code}\n```\n\n"
        "PREVIOUS TEST ATTEMPT (If applicable):\n```\n{previous_test}\n```\n\n"
        "EVALUATOR FEEDBACK (from previous attempt):\n{feedback}"
    )
])


# ==========================================
# ADVERSARY CODER PROMPT
# ==========================================
ADVERSARY_CODER_PROMPT = ChatPromptTemplate.from_messages([
    (
        "system", 
        "You are a senior application security engineer specializing in automated vulnerability discovery. "
        "Your objective is to write a targeted, highly malicious test script targeting the provided function.\n\n"
        "REQUIREMENTS:\n"
        "1. AUTHENTICATION RESILIENCE: Use the provided Seeded Credentials to assess authorization boundaries and test for privilege escalation.\n\n"
        "2. TARGETED FUZZING: Subject the function inputs to maliciously mutated data, boundary values, null bytes, "
        "excessively large payloads, and invalid encodings. Do NOT write infinite loops or massive data-generation "
        "engines. The test runs in a sandbox with a tight execution timeout.\n\n"
        "3. DEPENDENCY IMPLICATION: Analyze the function logic to identify implied dependencies (e.g., ORM calls, "
        "deserialization routines). Exploit known weaknesses typical for those operations.\n\n"
        "4. ASSERTION STRATEGY: Write explicit `assert` statements to capture silent data corruption, memory leaks, "
        "improper error handling, or state leakage.\n\n"
        "5. FORMATTING: Output ONLY the raw test script code inside a markdown code block."
    ),
    (
        "user", 
        "TARGET FUNCTION: {symbol_name}\n"
        "FILE PATH: {file_path}\n"
        "LANGUAGE: {language}\n\n"
        "TARGET SOURCE CODE:\n```\n{source_code}\n```\n\n"
        "SEEDED CREDENTIALS / ENVIRONMENT STATE:\n{env_state}\n\n"
        "PREVIOUS TEST ATTEMPT:\n```\n{previous_test}\n```\n\n"
        "EVALUATOR FEEDBACK:\n{feedback}"
    )
])

# ==========================================
# BASELINE EVALUATOR PROMPT
# ==========================================
BASELINE_EVALUATOR_PROMPT = ChatPromptTemplate.from_messages([
    (
        "system", 
        "Evaluate the provided Docker execution logs to determine if the baseline test successfully seeded the mock database and authentication state.\n\n"
        "RULES FOR VERDICTS:\n"
        "- SYNTAX_ERROR: The generated test script itself failed due to bad imports, missing mocks, or invalid python/testing syntax.\n"
        "- VULNERABILITY_FOUND: The test script appears structurally and syntactically valid, but the target application crashed or threw an unhandled exception (e.g., ValueError, TypeError) during the happy path.\n"
        "- SYSTEM_SECURE: The test exited cleanly (Exit 0).\n\n"
        "REQUIREMENTS:\n"
        "1. If SYNTAX_ERROR, output precise 'feedback' instructing the coder on exactly how to fix the provided test script.\n"
        "2. If VULNERABILITY_FOUND, explain the target application's crash in the 'feedback' field.\n"
        "3. If SYSTEM_SECURE, extract any printed tokens, mock IDs, or credentials from standard output into the JSON output. Leave 'feedback' empty."
    ),
    (
        "user", 
        "TARGET FUNCTION SOURCE:\n```\n{source_code}\n```\n\n"
        "EXECUTED TEST SCRIPT:\n```\n{current_test_script}\n```\n\n"
        "EXECUTION RESULTS:\n"
        "EXIT CODE: {exit_code}\n"
        "STDOUT:\n{stdout}\n"
        "STDERR:\n{stderr}\n"
    )
])

# ==========================================
# ADVERSARY EVALUATOR PROMPT
# ==========================================
ADVERSARY_EVALUATOR_PROMPT = ChatPromptTemplate.from_messages([
    (
        "system", 
        "Evaluate the provided Docker execution logs to determine if the malicious payload successfully uncovered a logic flaw in the target function.\n\n"
        "RULES FOR VERDICTS:\n"
        "- SYNTAX_ERROR: The test script failed (Exit > 0) due to a genuine Python/Docker syntax error or missing import, NOT because the target application crashed.\n"
        "- VULNERABILITY_FOUND: The target application crashed (e.g., 500 error) or the explicit adversarial `assert` statement was tripped.\n"
        "- SYSTEM_SECURE: The test exited cleanly (Exit 0). The attack failed and the system handled the payload gracefully.\n\n"
        "REQUIREMENTS:\n"
        "1. If SYNTAX_ERROR, output precise 'feedback' instructing the coder on exactly how to fix the provided test script.\n"
        "2. If SYSTEM_SECURE, analyze the target function and the failed test script, then suggest a brief, entirely new adversarial attack vector for the next attempt in the 'feedback' field.\n"
    ),
    (
        "user", 
        "TARGET FUNCTION SOURCE:\n```\n{source_code}\n```\n\n"
        "EXECUTED TEST SCRIPT:\n```\n{current_test_script}\n```\n\n"
        "EXECUTION RESULTS:\n"
        "EXIT CODE: {exit_code}\n"
        "STDOUT:\n{stdout}\n"
        "STDERR:\n{stderr}\n"
    )
])