"""The chat request contract checked before the pinned shell converts a request (audit B1, B2, B3)."""
import json
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
sys.path.insert(0, str(ROOT / 'vendor/Strata-macOS'))
from api_requests import RequestError, check_anthropic, check_openai, check_request, parse
from serve.frontend import anthropic_to_messages, openai_to_messages

USER = dict(role='user', content='hi')
OPENAI_VALID = [
    dict(messages=[USER]),
    dict(messages=[dict(role='system', content='be brief'), dict(role='developer', content=None),
                   dict(role='user', content=[dict(type='text', text='a'), dict(type='input_text', text='b'),
                                              dict(text='c'), dict(type='image_url', image_url='data:,'),
                                              dict(type='other')]),
                   dict(role='assistant', content='', reasoning_content='why', tool_calls=[
                       dict(function=dict(name='f', arguments='{"a": 1}')), dict(name='g', arguments={}),
                       dict(function=dict(name='h', arguments='  ')), dict(function=dict(name='i'))]),
                   dict(role='tool', content='result')],
         tools=[dict(type='function', function=dict(name='f'))], chat_template_kwargs=dict(enable_thinking=False),
         stream=True, stop=None, max_tokens=256, max_completion_tokens=256.0),
    dict(messages=[USER], stop='', temperature=0, top_p=0, min_p=1, frequency_penalty=-2, presence_penalty=2,
         repetition_penalty=1.1, top_k=-1, seed=-1, max_tokens=-1),
    dict(messages=[USER], stop=[], temperature=2, top_p=1, min_p=0, top_k=2**31 - 1, seed=2**32 - 1, max_tokens=0,
         stream=False, tools=None, chat_template_kwargs=None),
]
ANTHROPIC_VALID = [
    dict(messages=[USER], max_tokens=64),
    dict(system=[dict(type='text', text='be brief')], stop_sequences=[], max_tokens=10**9, messages=[
        dict(role='user', content=[dict(type='text', text='a'), dict(type='image', source={}),
                                   dict(type='tool_result', content=[dict(type='text', text='r')]),
                                   dict(type='tool_result', content=None), dict(type='other', text=7)]),
        dict(role='assistant', content=[dict(type='thinking', thinking='t'), dict(type='text'),
                                        dict(type='tool_use', name='f', input={}), dict(type='tool_use')])],
         tools=[dict(name='f')], temperature=1, top_k=40),
]
OPENAI_INVALID = [
    ([], 'the request must be an object'), (None, 'the request must be an object'),
    ('hi', 'the request must be an object'), ({}, 'messages must be a list'),
    (dict(messages=None), 'messages must be a list'), (dict(messages={}), 'messages must be a list'),
    (dict(messages=[]), 'messages must not be empty'), (dict(messages=['hi']), 'messages[0] must be an object'),
    (dict(messages=[dict(content='hi')]), 'messages[0].role'),
    (dict(messages=[dict(role='function', content='hi')]), 'messages[0].role'),
    (dict(messages=[dict(role='user', content=5)]), 'messages[0].content must be a string or a list'),
    (dict(messages=[dict(role='user', content={})]), 'messages[0].content must be a string or a list'),
    (dict(messages=[dict(role='user', content=['hi'])]), 'messages[0].content[0] must be an object'),
    (dict(messages=[dict(role='user', content=[dict(type='text', text=None)])]), 'messages[0].content[0].text'),
    (dict(messages=[dict(role='assistant', reasoning_content=1)]), 'messages[0].reasoning_content'),
    (dict(messages=[dict(role='assistant', tool_calls={})]), 'messages[0].tool_calls must be a list'),
    (dict(messages=[dict(role='assistant', tool_calls=['f'])]), 'messages[0].tool_calls[0] must be an object'),
    (dict(messages=[dict(role='assistant', tool_calls=[dict(function='f')])]), 'tool_calls[0].function must be'),
    (dict(messages=[dict(role='assistant', tool_calls=[dict(function=dict(name=1))])]), 'function.name'),
    (dict(messages=[dict(role='assistant', tool_calls=[dict(function=dict(arguments='{'))])]), 'not valid JSON'),
    (dict(messages=[dict(role='assistant', tool_calls=[dict(function=dict(arguments='[1]'))])]), 'JSON object'),
    (dict(messages=[dict(role='assistant', tool_calls=[dict(function=dict(arguments=[1]))])]), 'JSON object'),
    (dict(messages=[USER], tools=5), 'tools must be a list'), (dict(messages=[USER], tools=['f']), 'tools[0]'),
    (dict(messages=[USER], chat_template_kwargs=5), 'chat_template_kwargs must be an object'),
    (dict(messages=[USER], chat_template_kwargs='low'), 'chat_template_kwargs must be an object'),
    (dict(messages=[USER], stop='STOP'), 'stop is not supported'),
    (dict(messages=[USER], stop=['a']), 'stop is not supported'), (dict(messages=[USER], stop=7), 'stop is not'),
    (dict(messages=[USER], max_tokens=True), 'max_tokens must be an integer'),
    (dict(messages=[USER], max_tokens=1.7), 'max_tokens must be an integer'),
    (dict(messages=[USER], max_tokens='5'), 'max_tokens must be an integer'),
    (dict(messages=[USER], max_tokens=-2), 'max_tokens must be an integer'),
    (dict(messages=[USER], max_tokens=1e400), 'max_tokens must be an integer'),
    (dict(messages=[USER], max_completion_tokens=[1]), 'max_completion_tokens must be an integer'),
    (dict(messages=[USER], stream='false'), 'stream must be true or false'),
    (dict(messages=[USER], temperature=1e400), 'temperature must be a number from 0 to 2'),
    (dict(messages=[USER], temperature=-0.1), 'temperature'), (dict(messages=[USER], temperature=2.5), 'temperature'),
    (dict(messages=[USER], temperature=True), 'temperature'), (dict(messages=[USER], temperature='1'), 'temperature'),
    (dict(messages=[USER], top_p=-1), 'top_p must be a number from 0 to 1'), (dict(messages=[USER], top_p=1.5), 'top_p'),
    (dict(messages=[USER], min_p=2), 'min_p'), (dict(messages=[USER], frequency_penalty=3), 'frequency_penalty'),
    (dict(messages=[USER], presence_penalty=-3), 'presence_penalty'),
    (dict(messages=[USER], repetition_penalty=0), 'repetition_penalty must be a number above 0'),
    (dict(messages=[USER], top_k=1.5), 'top_k must be an integer'), (dict(messages=[USER], top_k=-2), 'top_k'),
    (dict(messages=[USER], top_k=2**31), 'top_k'), (dict(messages=[USER], seed=2**32), 'seed must be an integer'),
    (dict(messages=[USER], seed=-2), 'seed'), (dict(messages=[USER], seed=False), 'seed'),
]
ANTHROPIC_INVALID = [
    ([], 'the request must be an object'), (dict(system=5, messages=[USER]), 'system must be a string or a list'),
    (dict(system=[5], messages=[USER]), 'system[0] must be an object'), (dict(messages=None), 'messages must be a list'),
    (dict(messages=['hi']), 'messages[0] must be an object'), (dict(messages=[dict(content='hi')]), 'messages[0].role'),
    (dict(messages=[dict(role='system', content='hi')]), 'messages[0].role must be user or assistant'),
    (dict(messages=[dict(role='user')]), 'messages[0].content must be a string or a list of blocks'),
    (dict(messages=[dict(role='user', content=5)]), 'messages[0].content must be a string or a list of blocks'),
    (dict(messages=[dict(role='user', content=['hi'])]), 'messages[0].content[0] must be an object'),
    (dict(messages=[dict(role='user', content=[dict(type='text', text=None)])]), 'content[0].text'),
    (dict(messages=[dict(role='assistant', content=[dict(type='thinking', thinking=1)])]), 'content[0].thinking'),
    (dict(messages=[dict(role='assistant', content=[dict(type='tool_use', name=1)])]), 'content[0].name'),
    (dict(messages=[dict(role='assistant', content=[dict(type='tool_use', input=[])])]), 'content[0].input'),
    (dict(messages=[dict(role='user', content=[dict(type='tool_result', content=5)])]), 'content[0].content'),
    (dict(messages=[USER], tools=[dict(description='f')]), 'tools[0].name must be a string'),
    (dict(messages=[USER], tools=['f']), 'tools[0] must be an object'),
    (dict(messages=[USER], stop_sequences=['END']), 'stop_sequences is not supported'),
    (dict(messages=[USER], max_tokens=True), 'max_tokens must be an integer'),
    (dict(messages=[USER], temperature=float('inf')), 'temperature'),
]


class ApiRequestTests(unittest.TestCase):
    def test_valid_requests_pass_and_the_pinned_conversion_accepts_them(self):
        for check, convert, requests in ((check_openai, openai_to_messages, OPENAI_VALID),
                                         (check_anthropic, anthropic_to_messages, ANTHROPIC_VALID)):
            for request in requests:
                with self.subTest(request=request):
                    check(request)
                    convert(request)
                    int(request.get('max_completion_tokens') or request.get('max_tokens') or 0)

    def test_malformed_requests_name_the_field(self):
        for check, cases in ((check_openai, OPENAI_INVALID), (check_anthropic, ANTHROPIC_INVALID)):
            for request, message in cases:
                with self.subTest(check=check.__name__, request=request):
                    with self.assertRaises(RequestError) as caught:
                        check(request)
                    self.assertIn(message, str(caught.exception))
                    self.assertEqual(caught.exception.code, 400)

    def test_shapes_that_crash_the_pinned_conversion_are_refused_first(self):
        crashes = [(openai_to_messages, check_openai, []), (openai_to_messages, check_openai, dict(messages=None)),
                   (openai_to_messages, check_openai, dict(messages=['hi'])),
                   (openai_to_messages, check_openai, dict(messages=[USER], chat_template_kwargs=5)),
                   (anthropic_to_messages, check_anthropic, dict(messages=[dict(content='hi')])),
                   (anthropic_to_messages, check_anthropic, dict(system=5, messages=[USER]))]
        for convert, check, request in crashes:
            with self.subTest(request=request):
                with self.assertRaises((AttributeError, TypeError, KeyError)):
                    convert(request)
                with self.assertRaises(RequestError):
                    check(request)

    def test_json_body_refuses_non_numbers_and_malformed_text(self):
        for body, message in ((b'{"messages": [], "temperature": NaN}', 'NaN is not a JSON number'),
                              (b'{"seed": Infinity}', 'Infinity is not a JSON number'),
                              (b'{"seed": -Infinity}', '-Infinity is not a JSON number'),
                              (b'{"messages": ', 'not valid JSON'), (b'\xff\xfe\x00', 'not valid JSON'),
                              (b'[' * 100000 + b']' * 100000, 'not valid JSON')):
            with self.subTest(body=body[:40]):
                with self.assertRaisesRegex(RequestError, message):
                    parse(body)
        self.assertEqual(parse(b''), {})
        self.assertEqual(parse(b'{"temperature": 1e400}'), {'temperature': float('inf')})

    def test_only_the_chat_paths_are_checked(self):
        valid = json.dumps(OPENAI_VALID[0]).encode()
        check_request('/v1/chat/completions', valid)
        check_request('/v1/messages', valid)
        for path in ('/settings', '/v1/chat/completions?x=1', '/v1/completions', '/v1/messages/count_tokens'):
            with self.subTest(path=path):
                check_request(path, b'not json')
        for path in ('/v1/chat/completions', '/v1/messages'):
            with self.subTest(path=path), self.assertRaisesRegex(RequestError, 'messages must be a list'):
                check_request(path, b'')


if __name__ == '__main__':
    unittest.main()
