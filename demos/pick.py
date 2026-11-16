#!/usr/bin/env python3
"""Help the user pick a demo, in two turns, with numbers only from measured runs.

    python demos/pick.py --tool <id> --plan <id> [--model <name>]                    # turn 1: the question
    python demos/pick.py --tool <id> --plan <id> [--model <name>] --budget <answer>  # turn 2: the menu

Turn 1 asks what the user wants to spend, then says what a demo really costs on their plan: part of a usage
limit, dollars, or time on a local model. Turn 2 lists the demos with what each cost in runs measured on that
tool and plan (demos/costs.json; demos/MEASURING.md says how a run is measured). Where nothing is measured it
says so and suggests a small demo. It never estimates: an agent cannot read the user's meter, and a number made
up to reassure is a number the user acts on. The plans are core/plans.json's. Each turn ends on the agent stop
line (install.stop_line): an agent shows the output word for word and runs the next command only after the
user replies. Without --plan, for a tool that has plans, it lists them and stops (exit 2).
"""
from __future__ import annotations

import argparse
import re
import sys
from datetime import date
from pathlib import Path

sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parent))
import demolib as dl  # noqa: E402
from demolib import Demo, install, vocab  # noqa: E402

# Every subscription line that says what a demo costs in dollars carries the plan's credits clause: paid credits
# past the limit are possible on those plans (core/plans.json pay_past_limit), so "no dollars" alone is untrue.
CREDITS = {"possible": "no extra dollars unless you have credits turned on",
           "unknown": "no dollars from the plan itself, though whether credits can bill you past its limit is "
                      "unconfirmed",
           "n/a": "no extra dollars"}
STALE_MODELS_DAYS = 31  # MODELS.md asks for a monthly review
# How big a demo is, for "the largest that fits" and "the smallest": a teaching demo sits between small and medium.
RANK = {"S": 1, "teaching": 1.5, "M": 2, "L": 3}


def where(tool: str, plan: dict | None) -> str:
    v = vocab.VOCAB[tool]
    return f"{v.name} ({plan['label']})" if plan else v.name


def num(x: float) -> str:
    return f"{x:.2f}".rstrip("0").rstrip(".") if isinstance(x, float) else str(x)


def span(lo: float, hi: float, fmt) -> str:
    return fmt(lo) if lo == hi else f"{fmt(lo)}–{fmt(hi)}"


def cost(plan: dict | None, row: dict) -> float:
    """What one run spent, in the plan's meter: share of a weekly limit, dollars, or (on a local model) minutes."""
    meter = plan["meter"] if plan else "free"
    return row["meter_delta"]["weekly_pct"] if meter == "share" else row["meter_delta"]["usd"] if meter == "usd" \
        else row["wall_min"]


def amount(plan: dict | None, lo: float, hi: float) -> str:
    meter = plan["meter"] if plan else "free"
    if meter == "share":
        return f"{span(lo, hi, num)}% of a weekly limit"
    if meter == "usd":
        return span(lo, hi, lambda x: f"${x:.2f}")
    return f"{span(lo, hi, num)} minutes"


def cell_runs(rows: list[dict], tool: str, plan_id: str | None, demo: str) -> list[dict]:
    """The runs measured on this tool, plan and demo: the picker's display key. A run from any other cell never
    shows here, whatever it measured."""
    return [r for r in rows if r["tool"] == tool and r["plan"] == plan_id and r["demo"] == demo]


def cost_line(demo: Demo, runs: list[dict], tool: str, plan: dict | None, model: str | None) -> str:
    if not runs:
        return f"Not measured yet on {where(tool, plan)}."
    costs = [cost(plan, r) for r in runs]
    fails = sum(not dl.accept_counts(r["accept"])[0] for r in runs)
    models = sorted({r["model"] for r in runs})
    efforts = sorted({r["effort"] for r in runs})
    n = len(runs)
    s = (f"{amount(plan, min(costs), max(costs))} over {n} run{'s' if n != 1 else ''} ({', '.join(models)}, "
         f"{', '.join(efforts)} effort, latest {max(r['date'] for r in runs)}); {fails} of {n} failed the held-out "
         "check.")
    if model and model not in models:
        s += f" Measured on {', '.join(models)}, not yours."
    if any(r.get("synthetic") for r in runs):
        s += " (Synthetic test runs, not measurements.)"
    return s


def reassure(tool: str, plan: dict | None) -> str:
    if plan is None:
        return (f"How {where(tool, None)} bills you is not in the kit's list of plans, so it cannot say what a "
                "demo costs there.")
    # A plan's label is a name ("API key", "A local model through Ollama"), so it goes in brackets after the
    # tool's, never into the middle of a sentence.
    on, meter = where(tool, plan), plan["meter"]
    if meter == "share":
        return (f"Trick question: on {on}, a demo costs {CREDITS[plan['pay_past_limit']]}. It spends part of "
                "your usage limit instead.")
    if meter == "usd":
        return f"Not a trick question: on {on}, you pay for every token, so a demo costs real dollars."
    return (f"Trick question: on {on}, the model runs on your own machine and costs no dollars per token. What "
            "a demo costs you is time.")


def answer_prompt(plan: dict | None) -> str:
    if plan is None:  # no plan to say how it bills, so the question's own unit
        return "Answer in dollars, or say you are not sure."
    if plan["meter"] == "share":
        return ("Answer with how much of your weekly limit you are happy to spend on it, as a percentage, or say "
                "you are not sure.")
    if plan["meter"] == "usd":
        return "Answer in dollars, or say you are not sure."
    return "Answer with how many minutes you have for it, or say you are not sure."


def parse_budget(s: str) -> float | None:
    t = s.strip().lower()
    if re.search(r"\b(nothing|none|zero)\b", t):
        return 0.0
    m = re.search(r"\d+(?:\.\d+)?", t)
    return float(m.group()) if m else None


def next_words(tool: str, plan_id: str | None, model: str | None) -> list[str]:
    return (["demo", "pick", "--tool", tool] + (["--plan", plan_id] if plan_id else [])
            + (["--model", model] if model else []))


def run_cmd(words: list[str]) -> str:
    bash, ps = dl.launcher(*words)
    return f"Run `{bash}` (PowerShell: `{ps}`)"


def question(demos: list[Demo], rows: list[dict], tool: str, plan: dict | None, model: str | None) -> list[str]:
    plan_id = plan["id"] if plan else None
    measured = [(d, cell_runs(rows, tool, plan_id, d.name)) for d in demos]
    measured = [(d, runs) for d, runs in measured if runs]
    out = ["How many dollars do you want to spend on this?", "", reassure(tool, plan)]
    if measured:
        out += [f"Measured on {where(tool, plan)}:"] + [f"- {d.title}: {cost_line(d, runs, tool, plan, model)}"
                                                        for d, runs in measured]
    else:
        out.append(f"What a demo costs has not been measured yet on {where(tool, plan)}, so no number here would be "
                   "real. The next step suggests a small demo.")
    out += ["", answer_prompt(plan), "",
            install.stop_line("this question word for word",
                              run_cmd(next_words(tool, plan_id, model) + ["--budget", "<answer>"])
                              + ", with their answer in place of <answer>,")]
    return out


def menu(demos: list[Demo], rows: list[dict], tool: str, plan: dict | None, model: str | None, budget: str,
         today: date) -> list[str]:
    plan_id = plan["id"] if plan else None
    runs_of = {d.name: cell_runs(rows, tool, plan_id, d.name) for d in demos}
    out = [f"Demos for {where(tool, plan)}, smallest first:"]
    for d in demos:
        node = ", needs Node" if d.needs_node else ""
        out.append(f"- {d.title} ({d.size}{node}), `{d.name}`: {d.summary}. "
                   f"{cost_line(d, runs_of[d.name], tool, plan, model)}")
    out.append("")
    if plan and plan["meter"] == "share":
        out.append(f"On {where(tool, plan)}, a demo costs {CREDITS[plan['pay_past_limit']]}: it spends part of your "
                   "usage limit.")
    measured = sorted((d for d in demos if runs_of[d.name]), key=lambda d: RANK[d.tier])
    # The small demo with the fewest held-out checks, the least to build. The first by title, the rule before,
    # turned into one with five times the checks when a second small demo was added.
    small = min((d for d in demos if d.tier == "S"), key=lambda d: (d.accept_count, d.title), default=demos[0])
    if not measured:
        out.append(f"Nothing is measured yet on {where(tool, plan)}, so there is no real number to give you. Start "
                   f"with a small demo: {small.title} (`{small.name}`).")
    else:
        top = {d.name: max(cost(plan, r) for r in runs_of[d.name]) for d in measured}
        limit = parse_budget(budget)
        fits = [d for d in measured if limit is not None and top[d.name] <= limit]
        if limit is None:
            pick = measured[0]
            out.append(f"Without a number to go by, the smallest measured demo is {pick.title}, at most "
                       f"{amount(plan, top[pick.name], top[pick.name])} in its runs.")
        elif fits:
            pick = fits[-1]
            out.append(f"The largest demo whose costliest run fits your answer is {pick.title}, at most "
                       f"{amount(plan, top[pick.name], top[pick.name])}.")
        else:
            pick = min(measured, key=lambda d: top[d.name])
            out.append(f"No measured demo's costliest run fits your answer; the cheapest is {pick.title}, at most "
                       f"{amount(plan, top[pick.name], top[pick.name])}.")
        if plan and plan["meter"] == "share":
            meter_cmd = (f"`{plan['meter_cmd']}`" + ("" if plan["meter_cmd_confirmed"] else ", if it shows your limit,")
                         if plan["meter_cmd"] else "your usage page")
            out.append(f"That assumes at least {num(top[pick.name] + 5)}% of your week is left; if {meter_cmd} shows "
                       "less, pick smaller.")
        reviewed = dl.models_reviewed()
        if reviewed and (today - reviewed).days > STALE_MODELS_DAYS:
            out.append(f"The kit's MODELS.md was last reviewed on {reviewed}, over a month ago, so the models named "
                       "above may have been replaced since.")
    start = ["demo", "start", "<demo>", "--tool", tool]
    out += ["", install.stop_line("this menu word for word, ask which demo they want",
                                  run_cmd(start) + ", with the demo they chose in place of <demo>,")]
    return out


def choose_plan(tool: str, tool_plans: list[dict], model: str | None) -> list[str]:
    out = [f"Which {vocab.VOCAB[tool].name} plan is this on? What a demo costs depends on it. Run the line for yours:"]
    for p in tool_plans:
        bash, ps = dl.launcher(*next_words(tool, p["id"], model))
        out += [f"- {p['label']}:", f"    bash:       {bash}", f"    PowerShell: {ps}"]
    out.append(install.stop_line("this list word for word, ask which plan they are on",
                                 "Run the line for their plan"))
    return out


def main(argv: list[str] | None = None) -> int:
    for stream in (sys.stdout, sys.stderr):
        stream.reconfigure(errors="replace")
    ap = argparse.ArgumentParser(prog="pick.py", description="Help pick a demo, with numbers only from measured runs.")
    ap.add_argument("--tool", choices=sorted(vocab.VOCAB), help="the tool that will build it (default: the one the "
                    "install record names)")
    ap.add_argument("--plan", help="the plan id from core/plans.json (default: the install record's)")
    ap.add_argument("--model", help="the model the session runs, to compare with the measured runs")
    ap.add_argument("--budget", help="the user's answer to the first turn's question")
    ap.add_argument("--costs", type=Path, default=dl.COSTS, help=argparse.SUPPRESS)  # tests' own runs
    args = ap.parse_args(argv)
    rec, problem = dl.load_record_or_none()
    tool = args.tool
    if tool is None:
        tools = dl.global_tools(rec)
        if len(tools) != 1:
            print(f"error: {problem or 'the install record names ' + str(len(tools)) + ' tools'}, so this needs "
                  f"--tool ({', '.join(sorted(vocab.VOCAB))}).", file=sys.stderr)
            return 2
        tool = tools[0]
    tool_plans = dl.plans().get(tool, [])
    ids = [p["id"] for p in tool_plans]
    plan_id = args.plan or ((rec or {}).get("plan") if (rec or {}).get("plan") in ids else None)
    if tool_plans and plan_id is None:
        print("\n".join(choose_plan(tool, tool_plans, args.model)))
        return 2
    if plan_id is not None and plan_id not in ids:
        known = f"its plans are {', '.join(ids)}" if ids else "it has none there, so leave out --plan"
        print(f"error: {plan_id!r} is not a {tool} plan in core/plans.json; {known}.", file=sys.stderr)
        return 2
    plan = dl.plan_row(tool, plan_id)
    try:
        rows = dl.recent(dl.load_costs(args.costs), date.today())
    except dl.CostsError as e:
        print(f"error: {e}. No numbers are shown from a costs file that does not check out.", file=sys.stderr)
        return 1
    demos = dl.all_demos()
    if args.budget is None:
        lines = question(demos, rows, tool, plan, args.model)
    else:
        lines = menu(demos, rows, tool, plan, args.model, args.budget, date.today())
    print("\n".join(lines))
    return 0


if __name__ == "__main__":
    sys.exit(main())
