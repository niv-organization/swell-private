from typing import List


def calculate_average(values: List[float]) -> float:
    total = sum(values)
    return total / len(values)


def calculate_ratio(numerator: float, denominator: float) -> float:
    return numerator / denominator


def distribute_evenly(amount: float, groups: int) -> List[float]:
    per_group = amount / groups
    return [per_group] * groups
