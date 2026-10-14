"""The chat request shape both APIs accept, checked before the pinned shell converts a request.

The pinned conversion (``serve/frontend.py`` and the handler's ``_openai``/``_anthropic``) assumes
objects and lists where a client may send anything, so a wrong type raises outside its 400 path and
the client sees a dropped connection. Here such a request gets a 400 that names the field, as do
values the engine would otherwise receive coerced or unchecked. An accepted body reaches the pinned
handler unchanged; tools and images keep the template's own refusal.
"""

import json
import math
from collections.abc import Callable
from typing import Any, cast

JSONDict = dict[str, Any]
OPENAI_ROLES = ("system", "developer", "user", "assistant", "tool")
ANTHROPIC_ROLES = ("user", "assistant")
TEXT_PARTS = (None, "text", "input_text")  # Part types whose text the pinned shell joins.
BLOCK_TEXT = {"text": "text", "thinking": "thinking"}  # Anthropic block type -> its text field.
TOKEN_CAP = "an integer; 0 or -1 means the rest of the context"
# Sampling fields either API passes to the engine: (field, accepted, wording). llama-server keeps
# top_k as int32 (0 or less: no top-k limit) and the seed as uint32, where -1 also means random.
NUMBERS: tuple[tuple[str, Callable[[float], bool], str], ...] = (
    ("temperature", lambda value: 0 <= value <= 2, "a number from 0 to 2"),
    ("top_p", lambda value: 0 <= value <= 1, "a number from 0 to 1"),
    ("min_p", lambda value: 0 <= value <= 1, "a number from 0 to 1"),
    ("frequency_penalty", lambda value: -2 <= value <= 2, "a number from -2 to 2"),
    ("presence_penalty", lambda value: -2 <= value <= 2, "a number from -2 to 2"),
    ("repetition_penalty", lambda value: value > 0, "a number above 0"),
)
INTEGERS: tuple[tuple[str, int, int, str], ...] = (
    ("top_k", -1, 2**31 - 1, "an integer from -1 to 2147483647"),
    ("seed", -1, 2**32 - 1, "an integer from 0 to 4294967295, or -1 for a random seed"),
)


class RequestError(Exception):
    """A chat request refused with 400; the message names the field."""

    code = 400


def need(condition: bool, message: str) -> None:
    if not condition:
        raise RequestError(message)


def finite(value: object) -> bool:
    """A JSON number other than a boolean; json.loads reads 1e400 as infinity."""
    if isinstance(value, bool):
        return False
    return isinstance(value, int) or (isinstance(value, float) and math.isfinite(value))


def integral(value: object) -> bool:
    return finite(value) and (isinstance(value, int) or cast(float, value).is_integer())


def obj(value: object, label: str) -> JSONDict:
    need(isinstance(value, dict), f"{label} must be an object")
    return cast(JSONDict, value)


def items(value: object, label: str, *, required: bool = False) -> list[object]:
    """A JSON list; an absent or null optional list is empty."""
    if value is None and not required:
        return []
    need(isinstance(value, list), f"{label} must be a list")
    return cast(list[object], value)


def text_field(block: JSONDict, key: str, label: str, *, required: bool = False) -> None:
    if required or key in block:
        need(isinstance(block.get(key), str), f"{label}.{key} must be a string")


def check_parts(content: object, label: str) -> None:
    """Message text: a string, null, or a list of objects whose text fields are strings."""
    if content is None or isinstance(content, str):
        return
    need(isinstance(content, list), f"{label} must be a string or a list of parts")
    for index, part in enumerate(cast(list[object], content)):
        block = obj(part, f"{label}[{index}]")
        if block.get("type") in TEXT_PARTS:
            text_field(block, "text", f"{label}[{index}]")


def check_messages(body: JSONDict, check: Callable[[object, str], None]) -> None:
    messages = items(body.get("messages"), "messages", required=True)
    need(bool(messages), "messages must not be empty")
    for index, message in enumerate(messages):
        check(message, f"messages[{index}]")


def check_stop(value: object, field: str) -> None:
    """No engine path applies stop sequences yet: a request that sets one is refused, not quietly ignored."""
    need(value in (None, "", []), f"{field} is not supported by this Mac profile; remove it from the request")


def check_common(body: JSONDict, caps: tuple[str, ...]) -> None:
    """Output cap, stream flag and sampling values, the same for both APIs."""
    for key in caps:
        value = body.get(key)
        need(value is None or (integral(value) and value >= -1), f"{key} must be {TOKEN_CAP}")
    need(body.get("stream") is None or isinstance(body.get("stream"), bool), "stream must be true or false")
    for key, accepted, wording in NUMBERS:
        value = body.get(key)
        need(value is None or (finite(value) and accepted(value)), f"{key} must be {wording}")
    for key, low, high, wording in INTEGERS:
        value = body.get(key)
        need(value is None or (integral(value) and low <= value <= high), f"{key} must be {wording}")


def check_openai_call(call: object, label: str) -> None:
    function = obj(obj(call, label).get("function", call), f"{label}.function")
    text_field(function, "name", f"{label}.function")
    arguments = function.get("arguments")
    if isinstance(arguments, str) and arguments.strip():
        try:
            arguments = json.loads(arguments)
        except ValueError:
            raise RequestError(f"{label}.function.arguments is not valid JSON") from None
    elif isinstance(arguments, str):
        arguments = None
    need(arguments is None or isinstance(arguments, dict), f"{label}.function.arguments must be a JSON object")


def check_openai_message(message: object, label: str) -> None:
    fields = obj(message, label)
    need(fields.get("role") in OPENAI_ROLES, f"{label}.role must be one of {', '.join(OPENAI_ROLES)}")
    check_parts(fields.get("content"), f"{label}.content")
    need(
        fields.get("reasoning_content") is None or isinstance(fields["reasoning_content"], str),
        f"{label}.reasoning_content must be a string",
    )
    for index, call in enumerate(items(fields.get("tool_calls"), f"{label}.tool_calls")):
        check_openai_call(call, f"{label}.tool_calls[{index}]")


def check_openai(request: object) -> None:
    body = obj(request, "the request")
    check_messages(body, check_openai_message)
    for index, tool in enumerate(items(body.get("tools"), "tools")):
        obj(tool, f"tools[{index}]")
    kwargs = body.get("chat_template_kwargs")
    need(kwargs is None or isinstance(kwargs, dict), "chat_template_kwargs must be an object")
    check_stop(body.get("stop"), "stop")
    check_common(body, ("max_completion_tokens", "max_tokens"))


def check_anthropic_block(block: object, label: str) -> None:
    fields = obj(block, label)
    kind = fields.get("type")
    if kind in BLOCK_TEXT:
        text_field(fields, BLOCK_TEXT[kind], label)
    elif kind == "tool_use":
        text_field(fields, "name", label)
        need(fields.get("input") is None or isinstance(fields["input"], dict), f"{label}.input must be an object")
    elif kind == "tool_result":
        check_parts(fields.get("content"), f"{label}.content")


def check_anthropic_message(message: object, label: str) -> None:
    fields = obj(message, label)
    need(fields.get("role") in ANTHROPIC_ROLES, f"{label}.role must be user or assistant")
    content = fields.get("content")
    if isinstance(content, str):
        return
    need(isinstance(content, list), f"{label}.content must be a string or a list of blocks")
    for index, block in enumerate(cast(list[object], content)):
        check_anthropic_block(block, f"{label}.content[{index}]")


def check_anthropic(request: object) -> None:
    body = obj(request, "the request")
    check_parts(body.get("system"), "system")
    check_messages(body, check_anthropic_message)
    for index, tool in enumerate(items(body.get("tools"), "tools")):
        text_field(obj(tool, f"tools[{index}]"), "name", f"tools[{index}]", required=True)
    check_stop(body.get("stop_sequences"), "stop_sequences")
    check_common(body, ("max_tokens",))


CHECKS: dict[str, Callable[[object], None]] = {
    "/v1/chat/completions": check_openai,
    "/v1/messages": check_anthropic,
}


def parse(body: bytes) -> object:
    """The body as the pinned handler reads it, except that NaN and Infinity are not JSON numbers."""

    def refuse(name: str) -> object:
        raise RequestError(f"{name} is not a JSON number")

    try:
        return json.loads(body or b"{}", parse_constant=refuse)
    except (ValueError, RecursionError) as error:  # ValueError includes UnicodeDecodeError.
        raise RequestError(f"the request body is not valid JSON: {error}") from None


def check_request(path: str, body: bytes) -> None:
    """Raise RequestError for a malformed chat request; other paths are left to the pinned handler."""
    check = CHECKS.get(path)
    if check is not None:
        check(parse(body))
