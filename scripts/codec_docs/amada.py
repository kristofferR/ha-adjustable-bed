"""AMADA's profile block in the shared Okin N-frame guide."""
from custom_components.adjustable_bed.codec import okin_nframe as codec
from custom_components.adjustable_bed.profiles import amada as p

from ._common import _block, _hex, _table


def render() -> str:
    return _block(
        _table(('Role', 'UUID'), (
            ('Service', f'`{p.SERVICE_UUID}`'), ('Write without response', f'`{p.WRITE_UUID}`'),
            ('Notify or indicate', f'`{p.NOTIFY_UUID}`'),
        )),
        _table(('Selector', 'Value'), ((name.upper(), f'`{value:02X}`') for name, value in p.SELECTORS.items())),
        _table(('Command', 'AB frame', 'Schedule'), (
            (key, _hex(codec.frame40(word)),
             f'4 commands + {p.UTILITY_TAILS[key]} massage queries' if key in p.UTILITY_TAILS
             else 'single release' if key == 'stop' else 'held refresh')
            for key, word in p.AMADA.keys.items()
        )),
        _table(('Operation', 'Encoding / value'), (
            ('Refresh interval', f'{p.REFRESH_MS} ms'),
            ('Finite HA preset press', f'{p.RECALL_MS} ms, then STOP'),
            ('Save/reset gesture', f'{p.SAVE_MS} ms; successful save ends refresh without STOP'),
            ('Massage query', _hex(codec.request(0xB0))),
            ('Alarm query', _hex(codec.request(0xC0))),
            ('Explicit query', '4 copies; utility tails are listed above'),
            ('Startup / sync clock', 'clock ×4, massage query ×2, alarm query ×2'),
            ('Clock', '`07 04 month (year-2000) day weekday hour minute second`, Sunday=0'),
            ('Alarm', '`07 05 repeat type hour minute 00 enabled selector`'),
            ('Alarm actions', ', '.join(f'{key}={value}' for key, value in p.ALARM_MODES.items())),
            ('Name admission', f'case-insensitive `{p.NAME_PREFIX}*`, app choice only'),
        )),
    )


BLOCKS = [('docs/beds/okin-nframe.md', 'amada-controls', render)]
