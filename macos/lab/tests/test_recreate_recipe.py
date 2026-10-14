"""The documented fresh-clone chain makes every default-launcher prerequisite before a step needs it.

Prerequisites come from the scripts and config/, not from the documents: the engines and models each
preparation script verifies or reads, the registry's model sources and the default profile's arguments.
Nothing here builds, downloads or loads anything.
"""
import ast
import json
from pathlib import Path
import re
import shlex
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
from engines import supports_feature
from runtime_profiles import PROFILES

MARKER = '<!-- default-profile-chain -->'
REGISTRY = json.loads((ROOT / 'config/models.json').read_text())
VALUE_FLAGS = {'--jobs', '--engine'}
# The derived model each preparation step registers (prepare_draft.py computes its id from the argument).
MAKES = {('scripts/prepare_draft.py', 'q3'): 'mtp_q3', ('scripts/prepare_shared.py', None): 'mtp_shared_q3',
         ('scripts/prepare_shared_layout.py', None): 'mtp_shared_packed_q3'}


def chain(document):
    """The commands of each sh block placed directly after the marker, in document order."""
    text = (ROOT / document).read_text()
    blocks = re.findall(re.escape(MARKER) + r'\n```sh\n(.*?)```', text, re.S)
    return [tuple(shlex.split(line)) for block in blocks for line in block.splitlines() if line.strip()]


def step(command):
    """(script, first positional argument, options) for one documented command."""
    script = next(token for token in command if token.startswith('scripts/'))
    rest = list(command[command.index(script) + 1:])
    positional, options = [], {}
    while rest:
        token = rest.pop(0)
        if token in VALUE_FLAGS:
            options[token] = rest.pop(0)
        elif token.startswith('--'):
            options[token] = True
        else:
            positional.append(token)
    return script, positional[0] if positional else None, options


def literal_calls(script, names):
    """String literals passed to the named functions, including tuples a comprehension feeds them."""
    found = set()
    for node in ast.walk(ast.parse((ROOT / script).read_text())):
        if isinstance(node, ast.Call) and getattr(node.func, 'id', None) in names:
            found |= {arg.value for arg in node.args[:1] if isinstance(arg, ast.Constant)}
        if isinstance(node, (ast.DictComp, ast.ListComp, ast.SetComp, ast.GeneratorExp)):
            calls = [call for call in ast.walk(node) if isinstance(call, ast.Call)
                     and getattr(call.func, 'id', None) in names]
            if calls:
                for generator in node.generators:
                    if isinstance(generator.iter, ast.Tuple):
                        found |= {item.value for item in generator.iter.elts if isinstance(item, ast.Constant)}
    return found


def products(command):
    script, argument, options = step(command)
    engines = literal_calls(script, {'write_receipt'})
    if '--engine' in options:  # prepare_m5.py writes the receipt of the engine it is given.
        engines.add(options['--engine'])
    models = {argument} if script == 'scripts/download_models.py' else set()
    if (script, argument) in MAKES:
        models.add(MAKES[script, argument])
    return {'engines': engines, 'models': models}


def needs(command):
    script = step(command)[0]
    made = products(command)
    return {'engines': literal_calls(script, {'verify_engine', 'source_info'}) - made['engines'],
            'models': literal_calls(script, {'model_path'}) - made['models']}


def launcher_needs():
    arguments = PROFILES['balanced']['arguments']
    option = lambda flag: arguments[arguments.index(flag) + 1]
    # The model header check imports gguf-py from the baseline checkout.
    return {'engines': {option('--engine'), 'baseline'}, 'models': {arguments[0], option('--draft-model')}}


class RecreateRecipeTests(unittest.TestCase):
    def test_readme_and_recipe_list_the_same_chain(self):
        readme = chain('README.md')
        self.assertGreater(len(readme), 5)
        self.assertEqual(readme, chain('bench/M5-PREPARATION-RECIPE.md'))
        self.assertEqual(step(readme[0])[0], 'scripts/provision.py')
        self.assertEqual(step(readme[-1])[0], 'scripts/validate_offline.py')
        for command in readme:
            self.assertTrue((ROOT / step(command)[0]).is_file(), command)

    def test_each_step_runs_after_what_it_needs(self):
        made = {'engines': set(), 'models': set()}
        for command in chain('README.md'):
            for kind, required in needs(command).items():
                self.assertFalse(required - made[kind], f'{shlex.join(command)} runs before its {kind} exist')
            for kind, items in products(command).items():
                made[kind] |= items
        for kind, required in launcher_needs().items():
            self.assertFalse(required - made[kind], f'The default launcher needs {kind} the chain does not make')

    def test_every_step_is_needed_by_the_default_launcher(self):
        commands = chain('README.md')
        wanted = launcher_needs()
        for command in reversed(commands[:-1]):  # The final offline gate makes nothing.
            made = products(command)
            with self.subTest(command=shlex.join(command)):
                self.assertTrue(any(made[kind] & wanted[kind] for kind in made), 'Step is not needed')
            for kind, required in needs(command).items():
                wanted[kind] |= required

    def test_steps_match_the_registry_and_engine_features(self):
        for (script, _), model in MAKES.items():
            with self.subTest(model=model):
                self.assertIn(REGISTRY[model]['derived']['source_model'], literal_calls(script, {'model_path'}))
        for command in chain('README.md'):
            script, argument, _ = step(command)
            if script == 'scripts/download_models.py':
                self.assertNotIn('derived', REGISTRY[argument], 'download_models.py refuses derived models')
        arguments = PROFILES['balanced']['arguments']
        helper = REGISTRY[arguments[arguments.index('--draft-model') + 1]]['derived']
        self.assertTrue(supports_feature(arguments[arguments.index('--engine') + 1], helper['required_engine']))


if __name__ == '__main__':
    unittest.main()
