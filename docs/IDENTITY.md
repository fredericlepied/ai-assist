# Identity Configuration

The `identity.yaml` file allows you to personalize how ai-assist interacts with you by customizing the assistant's behavior, your information, and communication preferences.

## Location

The identity file is located at:
```
~/.ai-assist/identity.yaml
```

Or if using a custom config directory:
```
$AI_ASSIST_CONFIG_DIR/identity.yaml
```

## Auto-Reload

Changes to `identity.yaml` are automatically detected and applied without restarting ai-assist in both monitor and interactive modes.

## Configuration Structure

The identity file has three main sections: `user`, `assistant`, and `preferences`.

### Complete Example

```yaml
version: '1.0'

user:
  name: 'Alex'
  role: 'DevOps Engineer'
  organization: 'Acme Corp'
  timezone: 'America/New_York'
  context: |
    I work on the Cloud Platform team, focusing on CI/CD pipelines
    and infrastructure automation. My priorities are reliability,
    security, and developer experience.

assistant:
  nickname: 'Nexus'
  personality: |
    You are Nexus, a helpful AI assistant specialized in DevOps
    and cloud infrastructure. You provide clear, actionable advice
    and focus on best practices for reliability and security.

preferences:
  formality: 'professional'
  verbosity: 'concise'
  emoji_usage: 'moderate'
```

## Field Reference

### User Section

Configure information about yourself that the assistant will use for personalization.

#### `user.name` (string, default: "there")
Your name. Used in greetings and personalized responses.

**Examples:**
```yaml
name: 'Alex'
name: 'Sarah Chen'
```

#### `user.role` (string, optional)
Your job title or role.

**Examples:**
```yaml
role: 'DevOps Engineer'
role: 'Site Reliability Engineer'
role: 'Platform Architect'
```

#### `user.organization` (string, optional)
Your company or organization name.

**Examples:**
```yaml
organization: 'Acme Corp'
organization: 'Red Hat'
```

#### `user.timezone` (string, optional)
Your timezone (not currently used in logic, but stored for context).

**Examples:**
```yaml
timezone: 'America/New_York'
timezone: 'Europe/Paris'
timezone: 'UTC'
```

#### `user.context` (string, optional)
Detailed information about your work context, team structure, priorities, or anything else you want the assistant to know about your environment. This is added to the system prompt.

**Examples:**
```yaml
context: |
  I work on the OpenShift CI/CD team, focusing on pipeline
  reliability and test infrastructure. My main priorities are
  reducing flaky tests and improving developer feedback loops.
```

```yaml
context: |
  Engineering Manager for the Storage team at Red Hat.
  Responsible for Ceph and OpenShift Data Foundation.
  Team of 8 engineers across 3 time zones.
```

### Assistant Section

Customize the assistant's identity and behavior.

#### `assistant.nickname` (string, default: "Nexus")
The name the assistant uses to identify itself.

**Examples:**
```yaml
nickname: 'Nexus'
nickname: 'Atlas'
nickname: 'Helios'
```

#### `assistant.personality` (string, optional)
A custom system prompt that completely overrides the default personality. Use this for specialized behavior or domain expertise.

**Warning:** When set, this replaces the entire default personality. If not set, a personality is automatically generated from other fields.

**Examples:**
```yaml
personality: |
  You are Atlas, an AI assistant specialized in Kubernetes and
  cloud-native technologies. You provide expert guidance on
  container orchestration, service mesh, and GitOps practices.
  You always consider security and scalability in your advice.
```

```yaml
personality: |
  You are Helios, a friendly AI assistant focused on helping
  with DCI (Distributed CI) workflows. You're familiar with
  OpenShift testing, CI/CD pipelines, and test result analysis.
  You communicate clearly and help troubleshoot test failures.
```

### Preferences Section

Control the assistant's communication style.

#### `preferences.formality` (string, default: "professional")
How formal the assistant should be in responses.

**Options:**
- `professional` - Maintains a professional, business-appropriate tone
- `casual` - Communicates in a casual, friendly manner
- `friendly` - Warm and approachable, but still helpful

**Examples:**
```yaml
formality: 'professional'  # "I recommend reviewing the logs for errors."
formality: 'casual'        # "Let's check the logs for any errors."
formality: 'friendly'      # "I'd be happy to help you check the logs!"
```

#### `preferences.verbosity` (string, default: "concise")
How detailed responses should be.

**Options:**
- `concise` - Brief, to-the-point responses
- `detailed` - Provides detailed explanations when appropriate
- `verbose` - Comprehensive, thorough explanations

**Examples:**
```yaml
verbosity: 'concise'   # "The test failed due to timeout."
verbosity: 'detailed'  # "The test failed because it exceeded the 5-minute timeout. This suggests the service is slow to respond."
verbosity: 'verbose'   # "The test failed due to a timeout after 5 minutes. This typically indicates... [continues with detailed explanation]"
```

#### `preferences.emoji_usage` (string, default: "moderate")
How frequently emojis are used in responses.

**Options:**
- `none` - No emojis
- `minimal` - Only when they add clarity
- `moderate` - Occasionally to enhance communication
- `liberal` - Frequent emoji usage for engagement

**Examples:**
```yaml
emoji_usage: 'none'     # "Test passed."
emoji_usage: 'minimal'  # "Test passed ✓"
emoji_usage: 'moderate' # "✅ Test passed"
emoji_usage: 'liberal'  # "🎉 Test passed! ✅"
```

## Quick Start Templates

### Minimal Configuration

Just the basics:

```yaml
version: '1.0'
user:
  name: 'Your Name'
```

### Professional Setup

For enterprise/work environments:

```yaml
version: '1.0'

user:
  name: 'Your Name'
  role: 'Your Role'
  organization: 'Your Company'

preferences:
  formality: 'professional'
  verbosity: 'concise'
  emoji_usage: 'minimal'
```

### Specialized Assistant

For domain-specific expertise:

```yaml
version: '1.0'

user:
  name: 'Your Name'
  context: |
    Describe your work context, team structure,
    and main responsibilities here.

assistant:
  nickname: 'Atlas'
  personality: |
    You are Atlas, an expert in [your domain]. You provide
    clear, actionable guidance on [specific topics].
    You prioritize [your key values: security, reliability, etc.].

preferences:
  formality: 'professional'
  verbosity: 'detailed'
  emoji_usage: 'moderate'
```

## Creating Your Identity File

### Command Line

Use the built-in command to create a template:

```bash
ai-assist /identity-init
```

This creates a basic `identity.yaml` with default values that you can customize.

### Manual Creation

Create the file at `~/.ai-assist/identity.yaml` with your preferred editor:

```bash
mkdir -p ~/.ai-assist
cat > ~/.ai-assist/identity.yaml << 'EOF'
version: '1.0'
user:
  name: 'Your Name'
assistant:
  nickname: 'Nexus'
preferences:
  formality: 'professional'
  verbosity: 'concise'
  emoji_usage: 'moderate'
EOF
```

## Viewing Your Identity

Check your current identity configuration:

```bash
ai-assist /identity-show
```

## How Identity Affects the Assistant

The identity configuration influences:

1. **System Prompt** - The assistant's personality and behavior are set via the system prompt
2. **Greetings** - Personalized welcome messages in interactive mode
3. **Context** - The assistant is aware of your role, organization, and priorities
4. **Communication** - Response style matches your preferences

## Examples by Use Case

### DevOps Engineer

```yaml
version: '1.0'
user:
  name: 'Alex'
  role: 'DevOps Engineer'
  context: |
    I manage CI/CD pipelines for OpenShift clusters.
    Focus on automation, reliability, and reducing toil.
assistant:
  nickname: 'Nexus'
preferences:
  formality: 'professional'
  verbosity: 'detailed'
  emoji_usage: 'minimal'
```

### QE Engineer

```yaml
version: '1.0'
user:
  name: 'Sam'
  role: 'QE Engineer'
  context: |
    I work on test automation for storage solutions.
    Need help analyzing test failures and CI trends.
assistant:
  nickname: 'Atlas'
  personality: |
    You are Atlas, specialized in QE workflows and test analysis.
    You help troubleshoot test failures, identify patterns, and
    suggest fixes. You're familiar with DCI, OpenShift, and CI/CD.
preferences:
  formality: 'casual'
  verbosity: 'detailed'
  emoji_usage: 'moderate'
```

### Engineering Manager

```yaml
version: '1.0'
user:
  name: 'Jordan'
  role: 'Engineering Manager'
  organization: 'Red Hat'
  context: |
    I manage a team of 10 engineers working on container storage.
    I need help with project planning, status updates, and team metrics.
assistant:
  nickname: 'Nexus'
preferences:
  formality: 'professional'
  verbosity: 'concise'
  emoji_usage: 'none'
```

## Best Practices

1. **Start Simple** - Begin with just your name and preferences, add more later
2. **Use Context Wisely** - Include information that helps the assistant understand your priorities
3. **Match Your Style** - Choose preferences that feel natural to you
4. **Iterate** - Adjust preferences based on how responses feel
5. **Specialized Assistants** - Use custom personality for domain-specific expertise

## Troubleshooting

### Changes Not Applied

If changes to `identity.yaml` don't take effect:

1. **Check Syntax** - Ensure valid YAML format (use a YAML validator)
2. **Check Location** - Verify file is in correct config directory
3. **Restart** - In rare cases, restart ai-assist (though auto-reload should work)

### Invalid YAML

Common YAML mistakes:

```yaml
# ❌ Wrong: Missing quotes for multiline
context: This is a
  multiline string

# ✅ Correct: Use pipe for multiline
context: |
  This is a
  multiline string

# ❌ Wrong: Inconsistent indentation
user:
 name: 'Alex'
  role: 'Engineer'

# ✅ Correct: Consistent 2-space indentation
user:
  name: 'Alex'
  role: 'Engineer'
```

### Default Values

If a field is omitted, these defaults are used:

```yaml
version: '1.0'
user:
  name: 'there'
  role: 'Manager'
  organization: null
  timezone: null
  context: null
assistant:
  nickname: 'Nexus'
  personality: null  # Auto-generated from other fields
preferences:
  formality: 'professional'
  verbosity: 'concise'
  emoji_usage: 'moderate'
```

## Related Documentation

- **[README.md](../README.md)** - Main documentation
- **[MULTI_INSTANCE.md](MULTI_INSTANCE.md)** - Running multiple instances with different identities
- **[CONTRIBUTING.md](../CONTRIBUTING.md)** - Development setup
