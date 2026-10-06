"""Focused answer checks for both greedy and normal sampled prediction runs."""
import ast
import json

from lab import request


def check_triple(content):
    tree = ast.parse(content)
    allowed = (ast.Module, ast.FunctionDef, ast.arguments, ast.arg, ast.Return, ast.BinOp,
               ast.Mult, ast.Name, ast.Load, ast.Constant, ast.Expr)
    if any(not isinstance(node, allowed) for node in ast.walk(tree)):
        raise AssertionError("Unexpected syntax in the simple function")
    if len(tree.body) != 1 or not isinstance(tree.body[0], ast.FunctionDef) or tree.body[0].name != "triple":
        raise AssertionError("Expected one function named triple")
    scope = {"__builtins__": {"int": int}}
    exec(compile(tree, "<model-triple-probe>", "exec"), scope)
    assert [scope["triple"](n) for n in [-4, 0, 7]] == [-12, 0, 21]


def run_answer_checks(base, model):
    cases = [
        ("multiply", "What is 17 multiplied by 23? Reply with only the number.", "391", "text"),
        ("different-multiply", "What is 53 multiplied by 19? Reply with only the number.", "1007", "text"),
        ("sum", "Orion has 14 samples, Lyra has 17, and Draco has 9. Give only the total sample count.", "40", "text"),
        ("extract-json", 'The city is Reno, the count is 37, and active is true. Return exactly one JSON object with keys city, count, active. No prose or Markdown.', {"city": "Reno", "count": 37, "active": True}, "json"),
        ("sort-unique-json", "Sort [9, 2, 9, 5, 2] numerically and remove duplicates. Reply only with a JSON array, without Markdown.", [2, 5, 9], "json"),
        ("updated-label", "The old label was violet-730. It was replaced by blue-9173. Reply with only the current label.", "blue-9173", "text"),
        ("ledger", "Records: R07 label=cedar-18493; R19 label=violet-61052; R28 label=basil-27031. Give only the label for R19.", "violet-61052", "text"),
        ("python-function", "Write a Python function named triple with one argument n that returns n multiplied by 3. Reply with only Python code, without Markdown fences.", "triple(-4, 0, 7) == (-12, 0, 21)", "code"),
    ]
    checks = []
    for temperature in [0, 0.6]:
        for name, prompt, expected, kind in cases:
            response = request(base, "/v1/chat/completions", {"model": model,
                "messages": [{"role": "user", "content": prompt}], "temperature": temperature,
                "seed": 1234, "max_tokens": 96, "reasoning_effort": "none",
                "chat_template_kwargs": {"enable_thinking": False}})
            content = (response["choices"][0]["message"].get("content") or "").strip()
            check = {"name": name, "temperature": temperature, "prompt": prompt,
                     "expected": expected, "response": response, "passed": False}
            try:
                if kind == "json":
                    assert json.loads(content) == expected
                elif kind == "code":
                    check_triple(content)
                else:
                    assert content == expected
                assert response["choices"][0]["finish_reason"] == "stop"
                check["passed"] = True
            except Exception as error:
                check["error"] = f"{type(error).__name__}: {error}"
            checks.append(check)
            print(f"{'PASS' if check['passed'] else 'FAIL'} answer {name} at temperature {temperature}", flush=True)
    return checks
