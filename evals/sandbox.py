"""The same Cloud.execute Mock/patch boundary used by offline regression tests.

No OS primitive is reachable, even if the dispatch implementation changes.
"""
from contextlib import ExitStack, contextmanager
from unittest.mock import Mock, patch
from ultron.actions import TOOLS


def simulated_action(name, args):
    tool = next((t for t in TOOLS if t['name'] == name), None)
    if not tool or not isinstance(args, dict):
        raise ValueError('Unknown desktop action or invalid arguments.')
    schema = tool['parameters']
    if set(args) != set(schema['required']):
        raise ValueError('Tool arguments must match declared properties exactly.')
    for key, spec in schema['properties'].items():
        value = args[key]
        if not isinstance(value, str) or ('enum' in spec and value not in spec['enum']):
            raise ValueError('Unsupported action argument.')
        if name == 'search_web' and (not value.strip() or len(value) > 500):
            raise ValueError('Search query must contain 1–500 characters.')
    if name == 'open_app':
        return f"Requested opening {args['app']}."
    if name == 'search_web':
        return 'Opened search results. Their contents have not been read.'
    return f"Sent {args['action']} media key; response depends on the active player."


@contextmanager
def action_sandbox(dispatch=simulated_action):
    blocked = AssertionError('Real OS action blocked by evaluation sandbox.')
    with ExitStack() as stack:
        for target in ('ultron.actions.execute', 'ultron.actions.subprocess.Popen',
                       'ultron.actions.webbrowser.open', 'ultron.actions.os.startfile',
                       'ultron.actions.ctypes.windll'):
            stack.enter_context(patch(target, Mock(side_effect=blocked), create=True))
        action = stack.enter_context(patch('ultron.cloud.execute', Mock(side_effect=dispatch)))
        yield action
