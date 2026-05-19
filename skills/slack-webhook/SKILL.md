---
name: slack-webhook
description: Post messages to Slack channels via incoming webhooks
allowed-tools:
  - internal__execute_skill_script
---

# Slack Webhook Integration

Post messages to Slack channels using incoming webhooks. Supports dual-channel configuration for personal logs and team announcements.

## Configuration

Add webhook URLs to your `.env` file:

```bash
# Personal/logs channel (default) - used when no channel specified
SLACK_WEBHOOK_URL=https://hooks.slack.com/services/T00/B00/XXX

# Team/announcements channel - used when "team" or "équipe" mentioned
SLACK_TEAM_WEBHOOK_URL=https://hooks.slack.com/services/T00/B01/YYY
```

## Setup

1. **Enable script execution** (required for skills):
   ```bash
   # In .env
   AI_ASSIST_ALLOW_SCRIPT_EXECUTION=true
   ```

2. **Allow environment variables** for this skill:
   ```bash
   /skill/add_env slack-webhook SLACK_WEBHOOK_URL
   /skill/add_env slack-webhook SLACK_TEAM_WEBHOOK_URL
   ```

3. **Create webhooks in Slack**:
   - Go to https://api.slack.com/apps
   - Create an app → Incoming Webhooks
   - Add webhook to workspace and select channel
   - Copy webhook URL to `.env`

## Usage

### Natural Language (Automatic)

The agent automatically detects when you want to post to Slack:

**Personal channel (default):**
```
> Poste sur Slack: "Build terminé avec succès ✅"
> Log sur Slack: "Analyse complétée"
> Note sur Slack: "CILAB-456 nécessite un suivi"
```

**Team channel:**
```
> Alerte l'équipe sur Slack: "Production déployée"
> Annonce à l'équipe: "Nouvelle version disponible"
> Notifie l'équipe sur Slack: "CILAB-789 résolu"
```

Keywords triggering team channel: `équipe`, `team`, `annonce`, `alerte équipe`, `notifie l'équipe`

### Direct Script Execution

```bash
# Personal channel (default)
internal__execute_skill_script(
  skill_name="slack-webhook",
  script_name="post_message.py",
  args=["Mon message"]
)

# Team channel
internal__execute_skill_script(
  skill_name="slack-webhook",
  script_name="post_message.py",
  args=["--channel", "team", "Message pour l'équipe"]
)
```

## Script: post_message.py

**Arguments:**
- `--channel [default|team]` - Which webhook to use (default: `default`)
- `message` - The message text to post

**Environment variables required:**
- `SLACK_WEBHOOK_URL` - For default channel
- `SLACK_TEAM_WEBHOOK_URL` - For team channel (optional)

**Exit codes:**
- `0` - Success
- `1` - Configuration error (missing webhook URL)
- `2` - HTTP error (Slack API returned error)

## Markdown Formatting

Slack supports markdown in messages:

| Syntax | Rendered |
|--------|----------|
| `*bold*` | **bold** |
| `_italic_` | _italic_ |
| `~strike~` | ~~strike~~ |
| `` `code` `` | `code` |
| `>quote` | Quote block |
| `- item` | • Bullet |
| `:emoji:` | 😀 |

## Troubleshooting

**"SLACK_WEBHOOK_URL not configured"**
- Add webhook URL to `.env`
- Restart ai-assist

**"Script execution is disabled"**
- Set `AI_ASSIST_ALLOW_SCRIPT_EXECUTION=true` in `.env`
- Restart ai-assist

**"Permission denied"**
- Run: `/skill/add_env slack-webhook SLACK_WEBHOOK_URL`
- Run: `/skill/add_env slack-webhook SLACK_TEAM_WEBHOOK_URL`

**Messages not appearing in Slack:**
- Verify webhook URL is correct
- Test with: `curl -X POST -H 'Content-type: application/json' --data '{"text":"Test"}' YOUR_WEBHOOK_URL`
- Check Slack app is installed in workspace

## Security

- Webhook URLs stored in `.env` (gitignored)
- No secrets in code or logs
- Sandboxed script execution
- Per-skill environment variable allowlist

## Examples

```
# Simple notification
> Poste sur Slack: "Déploiement terminé ✅"

# Team alert
> Alerte l'équipe: "CILAB-456 bloqué, intervention requise"

# Integration with other tools
> Vérifie les jobs DCI en erreur et envoie un résumé sur Slack
> Cherche les tickets Jira bloqués et alerte l'équipe sur Slack
```
