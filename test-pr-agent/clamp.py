"""Small numeric range helpers."""


def clamp(value, low, high):
    if value < low:
        return low
    if value > high:
        return high
    return value


def in_range(value, low, high):
    return low <= value <= high


def rescale(value, src_low, src_high, dst_low, dst_high):
    ratio = (value - src_low) / (src_high - src_low)
    return dst_low + ratio * (dst_high - dst_low)
