from typing import Dict, List


def group_by_key(items: List[Dict], key: str) -> Dict[str, List[Dict]]:
    result = {}
    for item in items:
        value = item.get(key, "unknown")
        result.setdefault(value, []).append(item)
    return result


def truncate(text: str, max_length: int = 100) -> str:
    if len(text) <= max_length:
        return text
    return text[:max_length - 3] + "..."
