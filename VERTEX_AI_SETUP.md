# Vertex AI Setup for BOSS

## Quick Start

If you have Claude Code working via Vertex AI, you can use the same credentials with BOSS.

### 1. Set Environment Variables

```bash
export ANTHROPIC_VERTEX_PROJECT_ID='your-gcp-project-id'
# Region is optional - SDK will auto-select if not specified
```

### 2. Update .env File

```bash
# Use @ format for model names (IMPORTANT!)
BOSS_MODEL=claude-sonnet-4-5@20250929

# DCI credentials
DCI_CLIENT_ID=your_dci_client_id
DCI_API_SECRET=your_dci_api_secret
```

### 3. Authenticate with Google Cloud

```bash
gcloud auth application-default login
```

### 4. Test It

```bash
uv run boss query "What is 2+2?"
```

You should see:
```
Using Vertex AI: project=your-project-id (default region)
2+2 = 4
```

## Critical Information

### Model Name Format

**Vertex AI uses @ symbol for model versions, not dashes:**

✅ **Correct**: `claude-sonnet-4-5@20250929`
❌ **Wrong**: `claude-sonnet-4-5-20250929`

This is the most common issue when switching from Direct API to Vertex AI.

### Region Configuration

**Leave region blank** unless you have a specific requirement:

```bash
# Good - let SDK choose optimal region
export ANTHROPIC_VERTEX_PROJECT_ID='your-project-id'

# Only set region if you need a specific one
# export ANTHROPIC_VERTEX_REGION='us-east5'
```

The Anthropic SDK will automatically select the best region based on model availability.

## Troubleshooting

### Error: 404 Model Not Found

**Symptom:**
```
Publisher Model `projects/.../models/claude-sonnet-4-5-20250929` was not found
```

**Solution:**
Update your model name to use @ format instead of dashes:
```bash
BOSS_MODEL=claude-sonnet-4-5@20250929
```

### Error: Vertex AI API Not Enabled

**Symptom:**
```
❌ Vertex AI API is NOT enabled
```

**Solution:**
Enable the Vertex AI API in your project:
```bash
gcloud services enable aiplatform.googleapis.com --project=your-project-id
```

**Note:** You may need to contact your GCP administrator if you don't have permissions.

### Error: Authentication Failed

**Symptom:**
```
❌ Not authenticated
```

**Solution:**
Authenticate with Google Cloud:
```bash
gcloud auth application-default login
```

## Available Models

To discover which models are available in your project:

```bash
uv run python discover_vertex_models.py
```

Currently known working models:
- `claude-sonnet-4-5@20250929` (latest)
- `claude-3-5-sonnet@20240620`
- `claude-3-5-sonnet-v2@20241022`
- `claude-3-opus@20240229`
- `claude-3-sonnet@20240229`
- `claude-3-haiku@20240307`

## How We Discovered This

The key discovery was that Claude Code (this session!) uses the model `claude-sonnet-4-5@20250929` with @ symbol.

We tested it directly:
```python
from anthropic import AnthropicVertex

client = AnthropicVertex(project_id="your-project-id")
response = client.messages.create(
    model="claude-sonnet-4-5@20250929",  # Note the @ symbol!
    max_tokens=10,
    messages=[{"role": "user", "content": "Hi"}]
)
```

This worked immediately, confirming the @ format is correct for Vertex AI.

## Comparison: Direct API vs Vertex AI

| Feature | Direct API | Vertex AI |
|---------|-----------|-----------|
| **Auth** | API Key | Google Cloud |
| **Model Format** | `claude-sonnet-4-5-20250929` | `claude-sonnet-4-5@20250929` |
| **Region** | Auto-selected | Auto-selected (or specify) |
| **Billing** | Anthropic account | GCP billing |
| **Use Case** | Personal/Free tier | Enterprise/Company |

## Environment Variables Reference

```bash
# Required for Vertex AI
ANTHROPIC_VERTEX_PROJECT_ID=your-gcp-project-id

# Optional - SDK auto-selects if not set
ANTHROPIC_VERTEX_REGION=us-east5

# Model configuration (use @ format!)
BOSS_MODEL=claude-sonnet-4-5@20250929

# DCI credentials
DCI_CLIENT_ID=your_dci_client_id
DCI_API_SECRET=your_dci_api_secret
DCI_CS_URL=https://api.distributed-ci.io

# Optional: Jira
JIRA_API_TOKEN=your_jira_token
JIRA_URL=https://issues.redhat.com
```

## Testing Your Setup

Use the provided test scripts:

```bash
# Test configuration
python test_vertex_setup.py

# Check Vertex AI setup
bash check_vertex_setup.sh

# Discover available models
uv run python discover_vertex_models.py

# Quick test
uv run boss query "What is 2+2?"
```

## Success Indicators

When everything is working, you should see:

```
Using Vertex AI: project=your-project-id (default region)
[Your query response here]
```

If you see this, congratulations! BOSS is successfully using Vertex AI.
