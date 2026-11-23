"""Wire codecs: one module per proven bed wire format.

A codec owns transport roles, framing, checksums, command and response
encoding, and STOP or release frames. App profiles choose which commands to
send, with which payloads and timing. See ``docs/design/protocol-codecs.md``.
"""
