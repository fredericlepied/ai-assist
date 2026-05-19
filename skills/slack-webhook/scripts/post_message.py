#!/usr/bin/env python3
"""Post a message to Slack via incoming webhook.

This script posts messages to Slack channels using webhook URLs configured
in environment variables. Supports dual-channel setup (personal/team).

Environment Variables:
    SLACK_WEBHOOK_URL: Webhook for personal/default channel
    SLACK_TEAM_WEBHOOK_URL: Webhook for team/announcements channel

Exit Codes:
    0: Success
    1: Configuration error (missing webhook URL)
    2: HTTP error (Slack API error)
"""

import argparse
import json
import os
import sys
import urllib.request
from urllib.error import HTTPError, URLError


def post_to_slack(webhook_url: str, message: str) -> tuple[bool, str]:
    """Post message to Slack webhook.

    Args:
        webhook_url: Slack webhook URL
        message: Message text to post

    Returns:
        Tuple of (success: bool, error_message: str)
    """
    payload = {"text": message}
    data = json.dumps(payload).encode("utf-8")

    req = urllib.request.Request(
        webhook_url,
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    try:
        with urllib.request.urlopen(req, timeout=10) as response:
            if response.status == 200:
                return True, ""
            else:
                return False, f"HTTP {response.status}: {response.read().decode('utf-8')}"
    except HTTPError as e:
        error_body = e.read().decode("utf-8") if e.fp else "No error details"
        return False, f"HTTP {e.code}: {error_body}"
    except URLError as e:
        return False, f"Network error: {e.reason}"
    except Exception as e:
        return False, f"Unexpected error: {e}"


def main() -> int:
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Post a message to Slack via webhook",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--channel",
        choices=["default", "team"],
        default="default",
        help="Which channel to post to (default: default)",
    )
    parser.add_argument("message", help="Message text to post")

    args = parser.parse_args()

    # Get webhook URL based on channel
    if args.channel == "team":
        webhook_url = os.getenv("SLACK_TEAM_WEBHOOK_URL")
        if not webhook_url:
            print("Error: SLACK_TEAM_WEBHOOK_URL not configured in environment", file=sys.stderr)
            print("Add it to .env or use --channel default", file=sys.stderr)
            return 1
        channel_name = "team channel"
    else:
        webhook_url = os.getenv("SLACK_WEBHOOK_URL")
        if not webhook_url:
            print("Error: SLACK_WEBHOOK_URL not configured in environment", file=sys.stderr)
            print("Add it to .env file", file=sys.stderr)
            return 1
        channel_name = "default channel"

    # Post message
    success, error = post_to_slack(webhook_url, args.message)

    if success:
        print(f"✓ Message posted successfully to Slack ({channel_name})")
        return 0
    else:
        print(f"✗ Failed to post to Slack ({channel_name}): {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
