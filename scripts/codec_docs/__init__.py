"""Generated blocks of the codec guides, one module per codec family.

Each public module exports ``BLOCKS``: ``(guide, block name, renderer)``
entries, where the renderer returns the block's body from the family's codec
and profile data. ``scripts/generate_codec_docs.py`` discovers the modules, so
a family PR adds or edits only its own module. Shared helpers live in
``_common.py``.
"""
