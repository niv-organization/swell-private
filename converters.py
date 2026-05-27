from typing import Any, Dict, List


def flatten_dict(data: Dict[str, Any], prefix: str = "") -> Dict[str, Any]:
    result = {}
    for key, value in data.items():
        full_key = f"{prefix}.{key}" if prefix else key
        if isinstance(value, dict):
            result.update(flatten_dict(value, full_key))
        else:
            result[full_key] = value
    return result


def chunk_list(items: List[Any], size: int) -> List[List[Any]]:
    return [items[i:i + size] for i in range(0, len(items), size)]
