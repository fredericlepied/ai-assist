"""Identity management for ai-assist"""

import os
import yaml
from pathlib import Path
from typing import Optional
from pydantic import BaseModel, Field


class UserIdentity(BaseModel):
    """User identity information"""
    name: str = "there"
    role: str = "Manager"
    organization: Optional[str] = None
    timezone: Optional[str] = None


class AssistantIdentity(BaseModel):
    """Assistant identity information"""
    nickname: str = "Nexus"


class CommunicationPreferences(BaseModel):
    """Communication style preferences"""
    formality: str = "professional"  # professional, casual, friendly


class Identity(BaseModel):
    """Complete identity configuration"""
    version: str = "1.0"
    user: UserIdentity = Field(default_factory=UserIdentity)
    assistant: AssistantIdentity = Field(default_factory=AssistantIdentity)
    preferences: CommunicationPreferences = Field(default_factory=CommunicationPreferences)

    @classmethod
    def load_from_file(cls, path: Optional[Path] = None) -> "Identity":
        """Load identity from YAML file

        Args:
            path: Path to identity.yaml file. If None, uses ~/.ai-assist/identity.yaml

        Returns:
            Identity object (uses defaults if file doesn't exist)
        """
        if path is None:
            path = Path.home() / ".ai-assist" / "identity.yaml"

        if not path.exists():
            # Return default identity
            return cls()

        try:
            with open(path) as f:
                data = yaml.safe_load(f)

            if not data:
                return cls()

            return cls(**data)

        except (yaml.YAMLError, TypeError, ValueError) as e:
            print(f"Warning: Error loading identity from {path}: {e}")
            print("Using default identity")
            return cls()

    def save_to_file(self, path: Optional[Path] = None):
        """Save identity to YAML file

        Args:
            path: Path to identity.yaml file. If None, uses ~/.ai-assist/identity.yaml
        """
        if path is None:
            path = Path.home() / ".ai-assist" / "identity.yaml"

        # Ensure directory exists
        path.parent.mkdir(parents=True, exist_ok=True)

        with open(path, "w") as f:
            yaml.safe_dump(
                self.model_dump(),
                f,
                default_flow_style=False,
                sort_keys=False
            )

    def get_system_prompt(self) -> str:
        """Generate system prompt for Claude

        Returns:
            System prompt string that introduces the assistant
        """
        parts = [f"You are {self.assistant.nickname}, an AI assistant"]

        if self.user.name != "there":
            # Personalized introduction
            parts.append(f"helping {self.user.name}")

            if self.user.role:
                parts[-1] += f", a {self.user.role}"

            if self.user.organization:
                parts[-1] += f" at {self.user.organization}"

        prompt = " ".join(parts) + "."

        # Add communication style
        if self.preferences.formality == "professional":
            prompt += " You maintain a professional tone."
        elif self.preferences.formality == "casual":
            prompt += " You communicate in a casual, friendly manner."
        elif self.preferences.formality == "friendly":
            prompt += " You are warm and approachable in your communication."

        return prompt

    def get_greeting(self) -> str:
        """Get personalized greeting

        Returns:
            Greeting string
        """
        if self.user.name != "there":
            return f"Hello {self.user.name}, I'm {self.assistant.nickname}."
        else:
            return f"Hello, I'm {self.assistant.nickname}."


# Module-level cached identity
_identity: Optional[Identity] = None


def get_identity(reload: bool = False) -> Identity:
    """Get the current identity (cached)

    Args:
        reload: If True, reload from file instead of using cache

    Returns:
        Identity object
    """
    global _identity

    if _identity is None or reload:
        _identity = Identity.load_from_file()

    return _identity
