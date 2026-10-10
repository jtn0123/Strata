"""Reject invalid measurements before aggregation or percentage calculation."""
import math
import statistics

METRICS = ("generation_tok_s", "prompt_tok_s", "ttft_s", "wall_s")


def positive(value, label):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value <= 0:
        raise ValueError(f"{label}: expected a finite positive measurement, got {value!r}")
    return value


def counter(value, label):
    if type(value) is not int or value < 0:
        raise ValueError(f"{label}: expected a nonnegative integer counter, got {value!r}")
    return value


def case_metrics(case, cached=False):
    label = f"{case.get('workload', 'cached' if cached else 'case')}/{case.get('prompt_tokens', case.get('history_budget', '?'))}/repeat={case.get('repeat', '?')}"
    values = {"generation_tok_s": case["native_timings"]["predicted_per_second"],
              "prompt_tok_s": case["native_timings"]["prompt_per_second"],
              "ttft_s": case["ttft_s"], "wall_s": case["wall_s"]} if cached else case
    rates = {key: positive(values[key], f"{label}/{key}") for key in METRICS}
    timings = case["native_timings"] if cached else case["response"]["final"]["timings"]
    drafted = counter(timings.get("draft_n", 0), f"{label}/draft_n")
    accepted = counter(timings.get("draft_n_accepted", 0), f"{label}/draft_n_accepted")
    if accepted > drafted:
        raise ValueError(f"{label}: accepted draft count exceeds proposals")
    return rates, drafted, accepted


def metrics(cases, cached=False):
    if not cases:
        raise ValueError("Cannot aggregate an empty measured case set")
    samples = [case_metrics(case, cached) for case in cases]
    result = {key: positive(statistics.median(s[0][key] for s in samples), f"median/{key}") for key in METRICS}
    drafted, accepted = sum(s[1] for s in samples), sum(s[2] for s in samples)
    result["draft_acceptance_percent"] = 100 * accepted / drafted if drafted else None
    return result


def change(before, after):
    for name, values in (("control", before), ("candidate", after)):
        for key in METRICS:
            positive(values[key], f"{name}/{key}")
    result = {"generation_increase_percent": 100 * (after["generation_tok_s"] / before["generation_tok_s"] - 1),
            "prompt_increase_percent": 100 * (after["prompt_tok_s"] / before["prompt_tok_s"] - 1),
            "ttft_reduction_percent": 100 * (1 - after["ttft_s"] / before["ttft_s"]),
            "total_time_reduction_percent": 100 * (1 - after["wall_s"] / before["wall_s"])}
    if not all(math.isfinite(value) for value in result.values()):
        raise ValueError("Computed percentage is nonfinite; measurements cannot be compared")
    return result
