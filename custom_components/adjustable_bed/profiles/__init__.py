"""App profiles: typed data that drives a wire codec.

A profile records what one app, or one legacy route, does with its codec:
layouts, payload shapes, hold and release timing, memory slots and setup
schedules. Timing comes from that profile's own evidence and is never
shared. See ``docs/design/protocol-codecs.md``.
"""
