# User-Defined Periodic Tasks

ai-assist supports user-defined periodic tasks through a simple YAML configuration file. This allows you to create custom monitoring and automation workflows without writing code.

## Quick Start

1. Create `~/.ai-assist/tasks.yaml`:

```yaml
tasks:
  - name: "My First Task"
    interval: 5m
    prompt: "Check for DCI failures in the last hour"
```

2. Start ai-assist in monitoring mode:

```bash
ai-assist monitor
```

Your task will run every 5 minutes automatically!

## Task Definition Reference

### Required Fields

- **name**: Unique identifier for the task (string)
- **interval**: How often to run the task (string: "30s", "5m", "1h", "2h30m")
- **prompt**: Natural language instruction for the agent (string, can be multi-line)

### Optional Fields

- **description**: Human-readable description of what the task does (string)
- **enabled**: Whether the task is active (boolean, default: true)
- **conditions**: List of if/then rules for automated actions (list of objects)

### Full Example

```yaml
tasks:
  - name: "Critical Failures Monitor"
    description: "Monitor for critical DCI failures"
    enabled: true
    interval: 10m
    prompt: |
      Search for DCI jobs with status failure or error in the last hour.
      Provide a summary starting with "Found X failures".
    conditions:
      - if: "failures > 0"
        then:
          action: notify
          message: "⚠️ Found {failures} critical failures!"
          level: warning
```

## Interval Format

ai-assist supports two types of scheduling:

### 1. Simple Intervals

Run tasks at regular intervals:

| Format | Meaning | Seconds |
|--------|---------|---------|
| `30s` | 30 seconds | 30 |
| `5m` | 5 minutes | 300 |
| `1h` | 1 hour | 3600 |
| `90m` | 90 minutes | 5400 |
| `2h30m` | 2 hours 30 minutes | 9000 |
| `1h5m30s` | 1 hour 5 minutes 30 seconds | 3930 |

### 2. Time-Based Schedules (NEW!)

Run tasks at specific times on specific days:

**Format**: `<time> on <days>`

**Time Options**:
- Presets: `morning` (9:00), `afternoon` (14:00), `evening` (18:00), `night` (22:00)
- Specific time: `9:30`, `14:00`, `17:45` (24-hour format)

**Day Options**:
- Groups: `weekdays` (Mon-Fri), `weekends` (Sat-Sun)
- Specific days: `monday`, `tuesday`, `wednesday`, `thursday`, `friday`, `saturday`, `sunday`
- Short names: `mon`, `tue`, `wed`, `thu`, `fri`, `sat`, `sun`
- Multiple days: `monday,wednesday,friday`

**Examples**:

| Schedule | Meaning |
|----------|---------|
| `morning on weekdays` | 9:00 AM Monday-Friday |
| `afternoon on weekends` | 2:00 PM Saturday-Sunday |
| `9:30 on weekdays` | 9:30 AM Monday-Friday |
| `17:00 on friday` | 5:00 PM every Friday |
| `14:00 on monday,wednesday,friday` | 2:00 PM Mon/Wed/Fri |
| `evening on saturday,sunday` | 6:00 PM weekends |

## Writing Effective Prompts

The prompt is a natural language instruction for the ai-assist agent. You can use any capability the agent has access to through MCP tools.

### Examples

**DCI Monitoring:**
```yaml
prompt: |
  Search for DCI jobs with status failure or error created in the last 24 hours.
  For each job, provide:
  1. Job ID
  2. Component version
  3. Remote CI lab
  4. Error summary
```

**Jira Tracking:**
```yaml
prompt: |
  Search for Jira tickets in project CILAB that were updated in the last hour.
  List ticket keys and what changed.
```

**Combined Queries:**
```yaml
prompt: |
  1. Check DCI jobs for OCP 4.19.0 in the last 6 hours
  2. Check related Jira tickets
  3. Provide a summary of issues and status
```

## Conditions and Actions

Conditions allow you to trigger automated actions based on task results.

### Condition Syntax

Conditions use simple expressions:

```yaml
conditions:
  - if: "count > 5"          # Greater than
    then: { ... }

  - if: "failures >= 10"     # Greater or equal
    then: { ... }

  - if: "status == 'failed'" # Equals
    then: { ... }

  - if: "rate < 85"          # Less than
    then: { ... }

  - if: "message contains 'critical'"  # String contains
    then: { ... }
```

### Supported Operators

| Operator | Example | Description |
|----------|---------|-------------|
| `>` | `count > 5` | Greater than |
| `<` | `failures < 10` | Less than |
| `>=` | `rate >= 0.95` | Greater or equal |
| `<=` | `errors <= 3` | Less or equal |
| `==` | `status == 'failed'` | Equal to |
| `!=` | `type != 'warning'` | Not equal to |
| `contains` | `message contains 'critical'` | String contains |
| `not_contains` | `output not_contains 'success'` | String doesn't contain |

### Metadata Extraction

ai-assist automatically extracts values from agent responses for use in conditions:

**Patterns Recognized:**

- `"Found X items"` → `{count: X, items: X}`
- `"X failures detected"` → `{failures: X}`
- `"Success rate: X%"` → `{success_rate: X}`
- `"Status: X"` → `{status: "X"}`
- `"X updated"` → `{updated_count: X}`

**Example:**

If your agent responds with:
```
Found 5 failures in the last hour.
Success rate: 82.5%
```

The extracted metadata will be:
```python
{
  "failures": 5,
  "count": 5,
  "success_rate": 82.5
}
```

### Available Actions

#### 1. notify - Console Notification

Print a notification message to the console.

```yaml
then:
  action: notify
  message: "Alert: {count} failures detected"
  level: warning  # info, warning, or error
```

Supports placeholders:
- `{count}`, `{failures}`, `{success_rate}`, etc. - From extracted metadata
- `{date}` - Current date (YYYY-MM-DD)

#### 2. log - Write to Log File

Write a message to a log file in `~/.ai-assist/logs/`.

```yaml
then:
  action: log
  message: "Task completed: {result}"
  file: "custom.log"  # Optional, defaults to task name
```

#### 3. create_google_doc - Generate Document

Create a Google Doc with the task results.

```yaml
then:
  action: create_google_doc
  title: "Report - {date}"
  folder: "Reports"  # Optional folder name
```

#### 4. store_kg - Store in Knowledge Graph

Store results in the knowledge graph (future enhancement).

```yaml
then:
  action: store_kg
  entity_type: "custom_result"
  data:
    summary: "{output}"
    count: "{count}"
```

## Example Task Definitions

### Example 1: Simple Monitoring

```yaml
tasks:
  - name: "Quick Status Check"
    interval: 5m
    prompt: "Check for any DCI failures in the last 10 minutes"
```

### Example 2: With Notifications

```yaml
tasks:
  - name: "Failure Alert"
    interval: 10m
    prompt: |
      Search for DCI jobs with status failure or error in the last 15 minutes.
      Format: "Found X failures"
    conditions:
      - if: "failures > 0"
        then:
          action: notify
          message: "⚠️ {failures} new failures detected!"
          level: warning
```

### Example 3: Daily Report

```yaml
tasks:
  - name: "Daily Summary"
    interval: 24h
    prompt: |
      Analyze all DCI jobs from the last 24 hours.
      Provide:
      - Total jobs: X
      - Success rate: Y%
      - Top issues
    conditions:
      - if: "count > 0"
        then:
          action: create_google_doc
          title: "DCI Daily Report - {date}"
```

### Example 4: Multiple Conditions

```yaml
tasks:
  - name: "Tiered Alerts"
    interval: 15m
    prompt: |
      Check for failures. Report as "Found X failures".
    conditions:
      - if: "failures > 10"
        then:
          action: notify
          message: "🔴 CRITICAL: {failures} failures!"
          level: error

      - if: "failures > 5"
        then:
          action: log
          message: "High failure count: {failures}"

      - if: "failures > 0"
        then:
          action: notify
          message: "ℹ️ {failures} failures detected"
          level: info
```

### Example 5: Morning Standup (Weekdays Only)

```yaml
tasks:
  - name: "Morning Standup Check"
    interval: "morning on weekdays"
    prompt: |
      Check for urgent items at start of workday:
      1. Critical Jira tickets
      2. Failed DCI jobs from overnight
      3. Items needing immediate attention

      Format: "Found X urgent items"
    conditions:
      - if: "urgent_items > 0"
        then:
          action: notify
          message: "🌅 Morning briefing: {urgent_items} items need attention"
          level: warning
```

### Example 6: End of Day Summary (Fridays)

```yaml
tasks:
  - name: "Weekly Wrap-up"
    interval: "17:00 on friday"
    prompt: |
      Generate end-of-week summary:
      - Total DCI jobs this week
      - Success rate
      - Open critical issues
      - Accomplishments
    conditions:
      - if: "jobs > 0"
        then:
          action: create_google_doc
          title: "Weekly Summary - {date}"
```

### Example 7: Disabled Task

```yaml
tasks:
  - name: "Weekend Report"
    enabled: false  # Temporarily disabled
    interval: 24h
    prompt: "Generate weekend summary"
```

## Hot Reload

ai-assist automatically detects changes to `tasks.yaml` and reloads tasks without requiring a restart.

1. Edit `~/.ai-assist/tasks.yaml` while ai-assist is running
2. Save the file
3. Within 5 seconds, ai-assist will:
   - Detect the change
   - Validate the new configuration
   - Reload tasks
   - Continue monitoring with updated definitions

If there's an error in the new configuration, ai-assist will:
- Print an error message
- Keep running with the previous configuration
- Not crash or stop monitoring

## File Location

Tasks are loaded from: `~/.ai-assist/tasks.yaml`

If this file doesn't exist, ai-assist will run without user-defined tasks (only built-in monitors).

## State and History

Each task maintains:

- **State**: Last run time, success/failure status, extracted metadata
  - Location: `~/.ai-assist/state/task_<task_name>.json`

- **History**: Log of past executions
  - Location: `~/.ai-assist/state/history/task_<task_name>.jsonl`

- **Logs**: Custom log files (if using log action)
  - Location: `~/.ai-assist/logs/<filename>`

## Best Practices

### 1. Start with Simple Tasks

Begin with basic monitoring tasks without conditions:

```yaml
tasks:
  - name: "Test Task"
    interval: 5m
    prompt: "Check system status"
```

### 2. Use Descriptive Names

Good names help you understand what each task does:

```yaml
# Good
name: "Critical OCP 4.19 Failures Monitor"

# Less clear
name: "Task 1"
```

### 3. Format Prompts for Metadata Extraction

Help the agent provide structured output:

```yaml
prompt: |
  Search for failures.

  Please respond starting with: "Found X failures"
  Then provide details.
```

### 4. Test Conditions Incrementally

Start without conditions, verify the output, then add conditions:

```yaml
# Step 1: Test basic task
prompt: "Count failures"

# Step 2: Add conditions after verifying output format
conditions:
  - if: "failures > 0"
    then: { ... }
```

### 5. Use Appropriate Intervals

Balance between responsiveness and API usage:

- Critical monitoring: `5m` - `15m`
- Regular checks: `30m` - `1h`
- Daily summaries: `24h`

### 6. Disable Instead of Delete

Keep task definitions but disable them:

```yaml
tasks:
  - name: "Old Task"
    enabled: false  # Keep for reference
    interval: 1h
    prompt: "..."
```

## Troubleshooting

### Task Not Running

1. Check that `enabled: true` (or omitted, as true is default)
2. Verify YAML syntax is valid
3. Check ai-assist logs for errors
4. Ensure `~/.ai-assist/tasks.yaml` exists and is readable

### Conditions Not Triggering

1. Verify metadata is being extracted (check state file)
2. Test the condition manually with actual values
3. Ensure the agent response matches expected patterns
4. Check for typos in field names

### File Changes Not Detected

1. Ensure file is saved
2. Wait up to 5 seconds for detection
3. Check for YAML syntax errors (prevents reload)
4. Verify file path is `~/.ai-assist/tasks.yaml`

### Actions Not Executing

1. Verify condition is true (check extracted metadata)
2. Check action syntax in YAML
3. Look for error messages in console
4. Ensure required permissions (e.g., for log files)

## Advanced Usage

### Custom Metadata Extraction

Guide the agent to provide specific formats:

```yaml
prompt: |
  Analyze the data and respond in this format:
  - Critical count: X
  - Warning count: Y
  - Success rate: Z%

  Then provide details.
```

This creates metadata:
```python
{
  "critical_count": X,
  "warning_count": Y,
  "success_rate": Z
}
```

### Chaining Tasks (Future)

While not yet implemented, you can simulate task dependencies:

```yaml
tasks:
  - name: "Data Collection"
    interval: 1h
    prompt: "Collect data and save summary"
    conditions:
      - if: "count > 0"
        then:
          action: store_kg
          entity_type: "collected_data"

  - name: "Data Analysis"
    interval: 1h
    prompt: "Analyze previously collected data from knowledge graph"
```

## Migration from Environment Variables

If you were using environment variables for monitoring configuration:

**Old (Environment Variables):**
```bash
export JIRA_PROJECTS="CILAB,OPENSHIFT"
export DCI_QUERIES="status in ['failure']|..."
```

**New (tasks.yaml):**
```yaml
tasks:
  - name: "Jira Monitor"
    interval: 5m
    prompt: "Check Jira projects CILAB and OPENSHIFT for updates"

  - name: "DCI Failure Monitor"
    interval: 5m
    prompt: "Search DCI jobs with status failure or error"
```

Benefits:
- ✓ More flexible (any query, not just predefined patterns)
- ✓ Hot reload without restart
- ✓ Conditional actions
- ✓ Version controllable
- ✓ Easier to understand and modify

## See Also

- [QUICKSTART.md](QUICKSTART.md) - Getting started with ai-assist
- [README.md](README.md) - Overview and installation
- [examples/tasks.yaml](examples/tasks.yaml) - Example task definitions
