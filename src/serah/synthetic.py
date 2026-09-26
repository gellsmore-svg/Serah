"""Fictional ChatGPT-shaped history for the demo and tests.

No real conversation is represented here.
"""

from __future__ import annotations

from datetime import datetime, timezone


def _ts(month_day: int, hour: int, minute: int = 0) -> float:
    return datetime(2024, 3, month_day, hour, minute, tzinfo=timezone.utc).timestamp()


def demo_turns() -> list[dict]:
    """Current-branch turns, in order. One off-branch turn is added by the exporter."""
    return [
        {
            "id": "m-sys",
            "role": "system",
            "ts": _ts(1, 9, 0),
            "text": "You are a helpful assistant.",
        },
        {
            "id": "m-d1",
            "role": "user",
            "ts": _ts(1, 9, 30),
            "text": (
                "I woke up on edge. There is a low anxious hum about tomorrow "
                "and I feel uneasy, nothing dramatic."
            ),
        },
        {
            "id": "m-d1a",
            "role": "assistant",
            "ts": _ts(1, 9, 31),
            "text": "That sounds like a quiet kind of unease. What is tomorrow?",
        },
        {
            "id": "m-d2",
            "role": "user",
            "ts": _ts(2, 11, 0),
            "text": "This is getting frustrating. I keep hitting the same wall and I am fed up with it.",
        },
        {
            "id": "m-d2a",
            "role": "assistant",
            "ts": _ts(2, 11, 1),
            "text": "You sound absolutely furious about this.",
        },
        {
            "id": "m-d3",
            "role": "user",
            "ts": _ts(3, 9, 15),
            "text": (
                "I am furious. I cannot believe they spoke to me like that. "
                "The anger is right at the front."
            ),
        },
        {
            "id": "m-d3b",
            "role": "user",
            "ts": _ts(3, 18, 40),
            "text": (
                "I thought it had cooled, but I am still angry. "
                "Not screaming, but the anger is sitting in my chest."
            ),
        },
        {
            "id": "m-d4a",
            "role": "assistant",
            "ts": _ts(4, 11, 59),
            "text": "You sound furious and ashamed.",
        },
        {
            "id": "m-d4",
            "role": "user",
            "ts": _ts(4, 12, 0),
            "text": "The library closes at six. I renewed the book and left the receipt on the desk.",
        },
        {
            "id": "m-d5",
            "role": "user",
            "ts": _ts(5, 10, 0),
            "text": (
                "I feel grateful and hopeful. There is a quiet love in how they sat with me, "
                "and I am thankful."
            ),
        },
        {
            "id": "m-d5b",
            "role": "user",
            "ts": _ts(5, 16, 0),
            "text": "What stayed with me is love, not the argument. I feel calm and a bit of joy.",
        },
        {
            "id": "m-d6",
            "role": "user",
            "ts": _ts(6, 8, 30),
            "text": (
                "I have to finish this tonight. My stomach is tight and it feels urgent, "
                "like a duty I cannot leave it. I know I will feel relief once it is done, "
                "and I am a little afraid of dropping it."
            ),
        },
        {
            "id": "m-d8",
            "role": "user",
            "ts": _ts(8, 19, 0),
            "text": (
                "The same duty is back. My stomach is tight, it feels urgent, and I have to "
                "deal with it before I can rest. There is relief waiting once it is done. "
                "I feel anxious underneath."
            ),
        },
        {
            "id": "m-d11",
            "role": "user",
            "ts": _ts(11, 13, 20),
            "text": (
                "Third time this pattern shows up. Duty, a tight stomach, urgent, I have to "
                "fix it, and then relief once it is done. I am afraid of letting someone down."
            ),
        },
    ]


def to_chatgpt_export() -> list[dict]:
    """Build one conversation in the ChatGPT mapping shape, plus an unused branch."""
    turns = demo_turns()
    mapping: dict[str, dict] = {}
    parent = None
    for ordinal, turn in enumerate(turns):
        node_id = f"node-{turn['id']}"
        mapping[node_id] = {
            "id": node_id,
            "parent": parent,
            "children": [],
            "message": {
                "id": turn["id"],
                "author": {"role": turn["role"]},
                "create_time": turn["ts"],
                "content": {"content_type": "text", "parts": [turn["text"]]},
                "metadata": {},
            },
        }
        if parent is not None:
            mapping[parent]["children"].append(node_id)
        parent = node_id
    # Alternate branch the current_node path does not include.
    # Its user text would be anger evidence if branches were flattened.
    branch_parent = "node-m-d2a"
    branch_id = "node-branch-fury"
    mapping[branch_id] = {
        "id": branch_id,
        "parent": branch_parent,
        "children": [],
        "message": {
            "id": "m-branch-fury",
            "author": {"role": "user"},
            "create_time": _ts(2, 11, 5),
            "content": {
                "content_type": "text",
                "parts": ["I am furious and full of rage about a film I am only describing."],
            },
            "metadata": {"branch": "unused"},
        },
    }
    mapping[branch_parent]["children"].append(branch_id)
    # A non-text part on an otherwise empty node, so the importer records a warning.
    empty_id = "node-empty-image"
    mapping[empty_id] = {
        "id": empty_id,
        "parent": "node-m-d4",
        "children": [],
        "message": {
            "id": "m-empty-image",
            "author": {"role": "user"},
            "create_time": _ts(4, 12, 5),
            "content": {
                "content_type": "multimodal_text",
                "parts": [{"content_type": "image_asset_pointer", "asset_pointer": "file-demo"}],
            },
            "metadata": {},
        },
    }
    mapping["node-m-d4"]["children"].append(empty_id)
    current = "node-m-d11"
    return [
        {
            "id": "conv-demo",
            "conversation_id": "conv-demo",
            "title": "A made-up fortnight",
            "create_time": _ts(1, 9, 0),
            "update_time": _ts(11, 13, 20),
            "current_node": current,
            "mapping": mapping,
        }
    ]
