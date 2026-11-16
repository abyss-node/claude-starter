"""Pebble: a tiny habit tally.

A log is a list with one entry per day, oldest first. A truthy entry means the
habit was kept that day; a falsy one means it was missed.
"""


def count_done(days):
    """Return how many days in the log the habit was kept."""
    return sum(1 for day in days if day)


def completion_rate(days):
    """Return the share of days kept, from 0.0 to 1.0. An empty log is 0.0."""
    if not days:
        return 0.0
    return count_done(days) / len(days)
