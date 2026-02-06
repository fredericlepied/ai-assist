# Security Model

This document describes the security controls for Agent Skills script execution in ai-assist.

## Overview

Agent Skills can include executable scripts that Claude can run to perform tasks. **Script execution is disabled by default and requires explicit opt-in.**

## Security Controls

### 1. Disabled by Default

Script execution is **OFF** unless explicitly enabled. Enable it by adding to your `.env` file:

```bash
# In .env file
AI_ASSIST_ALLOW_SCRIPT_EXECUTION=true
```

Or via environment variable:

```bash
export AI_ASSIST_ALLOW_SCRIPT_EXECUTION=true
```

**Recommended**: Use `.env` for persistent configuration. This prevents accidental execution of untrusted code.

### 2. Permission Enforcement

Skills must explicitly declare script execution permission in their `SKILL.md` frontmatter:

```yaml
---
name: my-skill
description: My skill that uses scripts
allowed-tools: "internal__execute_skill_script"
---
```

**Note:** The `allowed-tools` field is **optional**. If not specified, skills with scripts are allowed to execute them by default (when script execution is globally enabled). Skills can explicitly restrict execution by setting `allowed-tools` to exclude `internal__execute_skill_script`.

### 3. Path Validation

All script paths are validated to prevent directory traversal attacks:

- Scripts must exist in the skill's `scripts/` directory
- Resolved paths must be within the skill directory
- Attempts to access `../../../etc/passwd` or similar are blocked

### 4. Environment Filtering

Sensitive environment variables are filtered before script execution:

**Filtered patterns:**
- `*API_KEY*`
- `*TOKEN*`
- `*SECRET*`
- `*PASSWORD*`
- `ANTHROPIC_*`
- `GOOGLE_*`
- `AWS_*`
- `AZURE_*`
- `GITHUB_TOKEN`
- `JIRA_*`

Scripts run with a clean environment containing only non-sensitive variables plus `PATH`.

### 5. Resource Limits

Scripts are constrained by resource limits:

- **Timeout:** 30 seconds (hard limit)
- **Output size:** 20KB maximum (truncated after)
- **Working directory:** Constrained to skill's `scripts/` directory

### 6. No Shell Injection

Scripts are executed using `subprocess.run()` with `shell=False`:

```python
# Secure: passes arguments as list
subprocess.run(["/path/to/script.py", "arg1", "arg2"], shell=False)

# NOT used: would allow shell injection
subprocess.run("script.py arg1 arg2", shell=True)  # NEVER USED
```

This prevents injection attacks via malicious arguments.

### 7. Execution Constraints

- Scripts run in the skill's `scripts/` directory (cwd)
- No network access restrictions (relies on system firewall)
- No CPU/memory limits (future enhancement)

## Threat Model

### What We Protect Against

✅ **Directory traversal attacks**
- Blocked by path validation

✅ **Environment variable leakage**
- API keys and secrets filtered

✅ **Infinite loops / DoS**
- 30-second timeout enforced

✅ **Memory exhaustion via output**
- 20KB output limit

✅ **Shell injection**
- `shell=False` prevents command injection

✅ **Unauthorized script execution**
- Permission system (`allowed-tools` field)

### What We Don't Protect Against

❌ **Malicious system calls**
- Scripts can still call `os.system()`, `subprocess.run()` internally
- **Mitigation:** Only install trusted skills

❌ **Network attacks**
- Scripts can make HTTP requests, connect to services
- **Mitigation:** Review skill code before installation

❌ **Filesystem access**
- Scripts have same permissions as user running ai-assist
- **Mitigation:** Run ai-assist with limited user permissions

❌ **Dependency vulnerabilities**
- Scripts may use vulnerable Python libraries
- **Mitigation:** Keep dependencies updated, use virtual environments

❌ **CPU/Memory exhaustion**
- Scripts can use 100% CPU or consume memory
- **Mitigation:** Monitor system resources (future: cgroups)

## Best Practices

### For Users

1. **Only install trusted skills**
   - Review skill code before installing
   - Prefer official skills from `anthropics/skills`
   - Check skill author/source

2. **Keep script execution disabled unless needed**
   - Only enable when you need to run scripts
   - Disable after use: `unset AI_ASSIST_ALLOW_SCRIPT_EXECUTION`

3. **Run with limited permissions**
   - Don't run ai-assist as root
   - Use a dedicated user account if processing sensitive data

4. **Review scripts before execution**
   - Check what the script does
   - Understand required dependencies
   - Verify it matches skill description

### For Skill Authors

1. **Declare all required tools**
   ```yaml
   allowed-tools: "internal__execute_skill_script Bash Read"
   ```

2. **Document dependencies clearly**
   ```yaml
   compatibility: Requires python3, python3-pypdf, python3-requests
   ```

3. **Write secure scripts**
   - Validate inputs
   - Handle errors gracefully
   - Avoid calling `eval()`, `exec()`
   - Use subprocess with `shell=False`

4. **Minimize scope**
   - Only request permissions you need
   - Keep scripts focused and simple
   - Document what each script does

5. **Test error cases**
   - Handle missing dependencies
   - Provide helpful error messages
   - Fail safely

## Dependency Management

Scripts may require external dependencies (Python libraries, system tools). ai-assist **does not install dependencies automatically**.

**User responsibility:**
1. Read the skill's `compatibility` field
2. Install required dependencies manually:
   ```bash
   # Example for PDF skill
   pip install pypdf pdfplumber
   # or
   apt install python3-pypdf python3-pdfplumber
   ```
3. Run the script
4. If execution fails, check error message for missing dependencies

**Why no automatic installation?**
- Security: prevents automatic execution of arbitrary installation code
- Simplicity: follows agentskills.io specification
- Transparency: users know exactly what's being installed

## Comparison to Other Execution Methods

| Method | Security | Use Case |
|--------|----------|----------|
| **Agent Skills Scripts** | Sandboxed, permission-based | Reusable skill-specific tools |
| **Internal Filesystem Tools** | Same as ai-assist process | File operations |
| **MCP Server Tools** | Separate process, protocol-isolated | External service integration |
| **Bash via prompt** | No sandboxing | Ad-hoc commands (requires user approval) |

## Security Validation Checklist

Before deploying script execution:

- [ ] Script execution disabled by default
- [ ] Skill declares `allowed-tools`
- [ ] Path validation prevents traversal
- [ ] Environment variables filtered
- [ ] Timeout enforced (30s)
- [ ] Output limited (20KB)
- [ ] `shell=False` used
- [ ] Tests verify all controls

## Reporting Security Issues

If you discover a security vulnerability in ai-assist script execution:

1. **Do not** open a public issue
2. Report via GitHub Security Advisories or email maintainers
3. Include:
   - Description of vulnerability
   - Steps to reproduce
   - Potential impact
   - Suggested fix (if any)

## Future Enhancements

Planned security improvements:

1. **Container sandboxing**
   - Run scripts in Docker containers
   - Complete filesystem isolation
   - Network restrictions

2. **Resource limits via cgroups**
   - CPU limits
   - Memory limits
   - Process limits

3. **Audit logging**
   - Log all script executions
   - Track which user ran what
   - Forensic analysis

4. **Code signing**
   - Verify skill signatures
   - Trusted skill registry
   - Automatic updates

## References

- [agentskills.io specification](https://agentskills.io/specification)
- [OWASP Command Injection](https://owasp.org/www-community/attacks/Command_Injection)
- [Python subprocess security](https://docs.python.org/3/library/subprocess.html#security-considerations)
