"""Build exact-token retrieval inputs; tokenization is supplied by the caller."""
import hashlib
import json
import random

SEEDS = (7, 23, 61)


def build(encode, render, budget=6144, seed=7):
    if not 1024 <= budget <= 7168: raise ValueError("Retrieval budget must leave room for output in 8K context")
    rng = random.Random(seed)
    expected = {key: f"{word}-{rng.randrange(10000, 99999)}" for key, word in
                zip(("start", "middle", "end"), ("amber", "cedar", "violet"))}
    markers = ("[[START_SLOT]]", "[[MIDDLE_SLOT]]", "[[END_SLOT]]")
    text = ("Read this reference ledger. Use only PRIMARY records; ordinary records are distractors.\n" +
            "\n".join(markers) + "\nReturn only a raw JSON object with keys start, middle, end and their PRIMARY values. "
            "Do not use Markdown or code fences. Your first character must be { and your last character must be }. No explanation.")
    rendered = render(text)
    parts, rest = [], rendered
    for marker in markers:
        if rest.count(marker) != 1: raise ValueError("Template changed retrieval markers")
        part, rest = rest.split(marker); parts.append(encode(part))
    parts.append(encode(rest))
    facts = [encode(f"\nPRIMARY {key}: {value}\n") for key, value in expected.items()]
    filler = encode("\n".join(f"Ordinary record {i}: parcel {rng.randrange(100, 999)} goes to shelf {rng.choice(('north', 'south', 'west', 'east'))}."
                            for i in range(budget//4)))
    fixed = sum(map(len, parts)) + sum(map(len, facts))
    padding = budget - fixed
    if padding < 128 or len(filler) < padding: raise ValueError("Tokenized fixture cannot meet the requested budget")
    first = budget // 2 - len(parts[0]) - len(facts[0]) - len(parts[1])
    second = padding - first
    if min(first, second) < 64: raise ValueError("Facts cannot be separated at this token budget")
    prompt = parts[0] + facts[0] + filler[:first] + parts[1] + facts[1] + filler[first:first+second] + parts[2] + facts[2] + parts[3]
    starts = [len(parts[0]), len(parts[0])+len(facts[0])+first+len(parts[1]), budget-len(parts[3])-len(facts[2])]
    if len(prompt) != budget: raise AssertionError("Retrieval fixture token count mismatch")
    return {"fixture_version": 2, "seed": seed, "prompt_tokens": budget, "prompt": prompt,
            "prompt_sha256": hashlib.sha256(json.dumps(prompt).encode()).hexdigest(),
            "expected": expected, "fact_start_token_positions": dict(zip(expected, starts)),
            "limits": "Three exact facts with distractors; bounded recall regression, not general long-context quality proof."}


def correct(text, expected):
    try: value = json.loads(text.strip())
    except (ValueError, TypeError): return False
    return value == expected


def run_checks(base, context, budget=6144):
    from lab import request
    from benchmark import stream_completion
    if context < budget + 192: raise ValueError("Retrieval prompt/output does not fit this context")
    def encode(text): return request(base, "/tokenize", {"content": text, "add_special": False, "parse_special": True})["tokens"]
    def render(text): return request(base, "/apply-template", {"messages": [{"role": "user", "content": text}],
        "chat_template_kwargs": {"enable_thinking": False}})["prompt"]
    cases = []
    for seed in SEEDS:
        fixture = build(encode, render, budget, seed)
        result = stream_completion(base, {"prompt": fixture["prompt"], "n_predict": 96, "stream": True,
            "cache_prompt": False, "temperature": 0, "seed": 1234, "return_tokens": True})
        count_matches = result["final"]["timings"]["prompt_n"] == budget
        passed = count_matches and correct(result["text"], fixture["expected"])
        cases.append({**fixture, "passed": passed, "response": result})
        if not passed: break
    return cases
