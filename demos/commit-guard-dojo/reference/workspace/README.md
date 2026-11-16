# Pebble

Pebble keeps a tally of the days you kept a habit. A log is a plain Python list
with one entry per day, oldest first: `True` for a day you kept it, `False` for a
day you missed.

## Functions

- `count_done(days)`: how many days you kept the habit.
- `completion_rate(days)`: the share of days kept, from 0.0 to 1.0.
- `longest_streak(days)`: the longest run of consecutive days kept; 0 for an empty log.

## Tests

Standard library only. From this folder:

```
python -m unittest discover -s tests
```
