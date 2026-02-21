"""Shared utilities for prompt handling."""


def extract_prompt_messages(result, conversation_history: list) -> list[str]:
    """Convert prompt result messages to conversation history entries.

    Returns list of content strings for display purposes.
    """
    contents = []
    for msg in result.messages:
        if hasattr(msg.content, "text"):
            content = msg.content.text
        else:
            content = str(msg.content)
        conversation_history.append({"role": msg.role, "content": content})
        contents.append(content)
    return contents
