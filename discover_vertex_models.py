#!/usr/bin/env python3
"""Discover available Claude models in Vertex AI"""

import sys
import os
from pathlib import Path

# Add ai_assist to path
sys.path.insert(0, str(Path(__file__).parent))

from ai_assist.config import get_config


def test_models():
    """Test different Claude model names on Vertex AI"""
    config = get_config()

    if not config.use_vertex:
        print("❌ Vertex AI is not configured.")
        print("Please set ANTHROPIC_VERTEX_PROJECT_ID")
        return 1

    print("="*70)
    print("Discovering Available Claude Models on Vertex AI")
    print("="*70)
    print(f"\nProject: {config.vertex_project_id}")
    print(f"Region: {config.vertex_region or 'SDK default'}")

    # Common Claude model names for Vertex AI
    # NOTE: Vertex AI uses @ format for model names (e.g., claude-sonnet-4-5@20250929)
    # NOT dash format (e.g., claude-sonnet-4-5-20250929)
    model_names = [
        # Claude Sonnet 4.5 (latest)
        "claude-sonnet-4-5@20250929",

        # Claude 3.5 Sonnet
        "claude-3-5-sonnet@20240620",
        "claude-3-5-sonnet-v2@20241022",

        # Claude 3 Opus
        "claude-3-opus@20240229",

        # Claude 3 Sonnet
        "claude-3-sonnet@20240229",

        # Claude 3 Haiku
        "claude-3-haiku@20240307",

        # Try the one currently configured
        config.model,
    ]

    print("\nTesting model availability...")
    print("-"*70)

    from anthropic import AnthropicVertex

    # Build vertex kwargs
    vertex_kwargs = {"project_id": config.vertex_project_id}
    if config.vertex_region:
        vertex_kwargs["region"] = config.vertex_region

    available_models = []

    for model_name in model_names:
        try:
            print(f"\nTrying: {model_name}")
            client = AnthropicVertex(**vertex_kwargs)

            # Try to send a minimal message to test if model exists
            response = client.messages.create(
                model=model_name,
                max_tokens=10,
                messages=[{"role": "user", "content": "Hi"}]
            )

            print(f"  ✅ SUCCESS - Model is available!")
            available_models.append(model_name)

        except Exception as e:
            error_str = str(e)
            if "404" in error_str or "NOT_FOUND" in error_str:
                print(f"  ❌ Not found")
            elif "403" in error_str or "PERMISSION_DENIED" in error_str:
                print(f"  ⚠️  Permission denied - model exists but access restricted")
            else:
                print(f"  ❌ Error: {error_str[:100]}")

    print("\n" + "="*70)
    print("Summary")
    print("="*70)

    if available_models:
        print(f"\n✅ Found {len(available_models)} available model(s):")
        for model in available_models:
            print(f"   • {model}")

        print(f"\n💡 To use one of these models, update your .env file:")
        print(f"   AI_ASSIST_MODEL={available_models[0]}")

        return 0
    else:
        print("\n❌ No models found!")
        print("\nPossible reasons:")
        print("  1. Vertex AI API not enabled in your project")
        print("  2. No access to Claude models in this project")
        print("  3. Wrong region selected")
        print("\nNext steps:")
        print("  1. Check if Vertex AI API is enabled:")
        print("     gcloud services list --enabled --project={config.vertex_project_id}")
        print("  2. Check available regions:")
        print("     Try setting ANTHROPIC_VERTEX_REGION to one of:")
        print("     - us-east5")
        print("     - us-central1")
        print("     - europe-west1")
        print("  3. Contact your GCP admin to enable Claude on Vertex AI")

        return 1


if __name__ == "__main__":
    sys.exit(test_models())
