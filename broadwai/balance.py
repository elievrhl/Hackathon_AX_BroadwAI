"""Preserve a general-interest edition while personalizing its individual readings."""

import math
from collections import defaultdict


def interest_balance(profile, size):
    topics = list(dict.fromkeys(i.topic for i in profile.interests))
    return {
        "interests": [
            {"id": f"interest-{n + 1}", "topic": topic} for n, topic in enumerate(topics)
        ],
        "max_per_interest": math.ceil(size / min(3, len(topics))) if len(topics) > 1 else size,
        "minimum_per_interest": min(2, size // len(topics)),
    }


def interleave(selections, group):
    buckets = defaultdict(list)
    for selection in selections:
        buckets[group(selection)].append(selection)
    return [
        bucket[index]
        for index in range(max(map(len, buckets.values()), default=0))
        for bucket in buckets.values()
        if index < len(bucket)
    ]
