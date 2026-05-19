# Slack Webhook Skill - Setup Guide

Quick guide to enable Slack notifications in ai-assist using the `slack-webhook` skill.

## Why a Skill?

The Slack integration is implemented as an **Agent Skill** rather than core functionality:

- ✅ **Zero core code changes** - no modifications to `agent.py` or internal tools
- ✅ **Opt-in and modular** - only loaded if you install/enable it
- ✅ **Easy to maintain** - standalone script and documentation
- ✅ **Follows agentskills.io** - standard skill pattern

## Quick Start (5 minutes)

### 1. Create Slack Webhook

1. Go to https://api.slack.com/apps
2. Click **"Create New App"** → **"From scratch"**
3. Name it (e.g., `ai-assist`) and select your workspace
4. Go to **"Incoming Webhooks"** → Enable it
5. Click **"Add New Webhook to Workspace"**
6. Select channel (e.g., `#logs` for personal, `#general` for team)
7. **Copy the webhook URL**

Repeat for a second webhook if you want separate personal/team channels.

### 2. Configure ai-assist

Edit `.env`:

```bash
# Enable script execution (required for skills)
AI_ASSIST_ALLOW_SCRIPT_EXECUTION=true

# Slack webhooks
SLACK_WEBHOOK_URL=https://hooks.slack.com/services/T00/B00/XXX
SLACK_TEAM_WEBHOOK_URL=https://hooks.slack.com/services/T00/B01/YYY  # Optional
```

### 3. Allow Environment Variables

Launch ai-assist and run:

```bash
/skill/add_env slack-webhook SLACK_WEBHOOK_URL
/skill/add_env slack-webhook SLACK_TEAM_WEBHOOK_URL
```

This allows the skill's script to access these environment variables.

### 4. Test It

```
> Poste sur Slack: "Test message from ai-assist"
```

You should see the message in your configured Slack channel!

## Usage Examples

### Personal Logs (Default Channel)

```
> Poste sur Slack: "Build terminé avec succès ✅"
> Log sur Slack: "Analyse complétée, 5 anomalies détectées"
> Note sur Slack: "CILAB-456 nécessite un suivi demain"
```

### Team Announcements

```
> Alerte l'équipe sur Slack: "Production déployée"
> Annonce à l'équipe: "Nouvelle version v2.1.0 disponible"
> Notifie l'équipe sur Slack: "CILAB-789 résolu"
```

The agent automatically selects the team webhook when you mention:
- `équipe`, `team`, `annonce`, `alerte équipe`, `notifie l'équipe`

### Integration with Tools

```
> Vérifie les jobs DCI en erreur et envoie un résumé sur Slack
> Cherche les tickets Jira bloqués et alerte l'équipe sur Slack
> Analyse les changements dans le KG et poste un rapport sur Slack
```

## How It Works

1. **Agent detects Slack request** from natural language
2. **Agent calls** `internal__execute_skill_script` tool
3. **Skill script** `post_message.py` executes:
   - Reads webhook URL from environment
   - Posts message via HTTP
   - Returns success/error
4. **Agent reports** result to you

## Troubleshooting

### Skill Not Found

**Symptom:** Agent says "slack-webhook skill not installed"

**Solution:** The skill should be auto-loaded from `skills/slack-webhook/`. Verify:
```bash
ls -la skills/slack-webhook/
# Should show: SKILL.md, scripts/post_message.py
```

### Script Execution Disabled

**Symptom:** "Error: Script execution is disabled"

**Solution:** Add to `.env`:
```bash
AI_ASSIST_ALLOW_SCRIPT_EXECUTION=true
```

Then restart ai-assist.

### Permission Denied

**Symptom:** "Error: Skill 'slack-webhook' not allowed to execute scripts"

**Solution:** Allow environment variables:
```bash
/skill/add_env slack-webhook SLACK_WEBHOOK_URL
/skill/add_env slack-webhook SLACK_TEAM_WEBHOOK_URL
```

### Webhook Not Configured

**Symptom:** "SLACK_WEBHOOK_URL not configured"

**Solution:** Add webhook URL to `.env` and restart ai-assist.

### Messages Not Appearing

**Symptom:** Script reports success but no message in Slack

**Solution:**
1. Verify webhook URL is correct
2. Test manually:
   ```bash
   curl -X POST -H 'Content-type: application/json' \
     --data '{"text":"Manual test"}' \
     YOUR_WEBHOOK_URL
   ```
3. Check Slack app is installed in workspace
4. Verify you're looking at the correct channel

## Security

- **Webhook URLs** are stored in `.env` (gitignored by default)
- **Sandboxed execution** - script runs with filtered environment
- **Per-skill allowlist** - only explicitly allowed env vars are passed
- **No shell access** - script cannot execute arbitrary commands
- **Timeout protection** - 30-second execution limit

## Advanced: Direct Script Usage

If you need to call the script directly (for debugging or automation):

```bash
# Personal channel
python3 skills/slack-webhook/scripts/post_message.py "My message"

# Team channel
python3 skills/slack-webhook/scripts/post_message.py --channel team "Team message"
```

Make sure environment variables are set before running.

## Comparison with Core Integration

**Skill approach** (current):
- ✅ No core code changes
- ✅ Modular and opt-in
- ✅ Easy to remove/disable
- ✅ Follows project patterns
- ⚠️ Requires script execution enabled
- ⚠️ Extra setup step (env allowlist)

**Core integration** (alternative):
- ❌ Modifies `agent.py` and internal tools
- ❌ Always loaded (even if not configured)
- ❌ Harder to maintain
- ✅ No extra security setup
- ✅ Slightly simpler for end-user

The skill approach was chosen to keep ai-assist core clean and focused.

## Next Steps

- **Multiple channels?** Create more webhooks and add env vars
- **Rich formatting?** Slack supports markdown (see SKILL.md)
- **Bidirectional?** Consider the official [Slack MCP server](https://github.com/modelcontextprotocol/servers/tree/main/src/slack)

---

**Skill location:** `skills/slack-webhook/SKILL.md`
**Script location:** `skills/slack-webhook/scripts/post_message.py`
