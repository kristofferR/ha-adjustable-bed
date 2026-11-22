"""Guards for the clean-room analysis isolation boundary.

Clean-room APK analyses (issues #436, #443, #447) require that an analyst subagent recovers a
protocol from the artifact alone. Claude Code auto-injects ``CLAUDE.md`` into subagents based on
working directory, so an instruction file sitting above a run's workspace silently becomes
evidence. That happened twice: ``com.leggett.prodigy4`` run 1 was rejected and discarded, and
``de.octoactuators.octosmartcontrolapp`` was registered PARTIAL.

These tests exist because the dangerous file cannot be caught by review. ``disassembly/`` is
gitignored in full, and ``.gitignore``'s ``CLAUDE.md`` entry has no leading slash so it matches at
every depth. A reintroduced symlink would therefore be invisible in a diff forever. Only a
filesystem check can see it.

Pure filesystem and regex work: no Home Assistant imports, no fixtures, sub-second.
"""

from __future__ import annotations

import json
import os
import re
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]

# Directories that legitimately contain their own checkout or vendored tree. ``.claude`` is
# deliberately absent: Claude Code treats a file there as project instructions, so pruning it would
# leave ``.claude/CLAUDE.md`` able to carry protocol material to every analyst unseen. The walk only
# retains the two instruction filenames, so descending into it costs nothing.
_PRUNED = {
    ".git",
    ".venv",
    ".worktrees",
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
    "node_modules",
    "smartbed-mqtt",
    "smartbed-mqtt-discord-chats",
}

# Worktree containers, pruned by relative path rather than by name. Each holds full checkouts whose
# own root AGENTS.md is legitimate, so they are skipped, while ``.claude`` itself is still scanned
# for the project instruction file that would be injected from there.
_PRUNED_PATHS = {".claude/worktrees"}

# Filenames a harness auto-injects based on working directory. Outside the repo root, either one
# is an ancestor of a run workspace and reaches the analyst unbidden.
_INJECTED_FILENAMES = frozenset({"CLAUDE.md", "AGENTS.md"})

# Instruction files that the harness may inject into a clean-room analyst, plus the documents we
# hand it deliberately. All must be free of protocol values. The schema is copied into every run's
# input/, so a UUID or packet example added to a description or default would contaminate the run
# just as surely as one in the prompt.
_TRACKED_ANALYST_DOCS = (
    "docs/apk-analysis/TOOLING.md",
    "docs/apk-analysis/phase4-analyst-prompt.md",
    "docs/apk-analysis/analysis.schema.json",
)


def _analyst_visible_docs() -> tuple[str, ...]:
    """Return every document the analyst can see, including untracked root instruction files.

    The walk above deliberately permits instruction files at the repo root, so their *contents*
    have to be scanned instead. ``CLAUDE.md`` is gitignored at every depth, so a machine-local root
    copy (or a symlink to something else entirely) would otherwise carry protocol answers into
    every analyst while remaining invisible to both review and this guard.
    """
    roots = [name for name in sorted(_INJECTED_FILENAMES) if (REPO_ROOT / name).is_file()]
    return (*roots, *_TRACKED_ANALYST_DOCS)


_ANALYST_VISIBLE_DOCS = _analyst_visible_docs()

_UUID = re.compile(r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}")
# A short UUID is only recognisable from its label, and "Service: FFE0" is as much an answer as the
# full 128-bit form, so the surrounding GATT vocabulary is part of the signal.
_UUID_CONTEXT = re.compile(r"\b(?:uuid|service|characteristic|descriptor)s?\b", re.IGNORECASE)
# A short-form UUID is 4, 8 or 32 hex digits containing both a letter and a numeral. All three
# constraints earn their place: the fixed lengths rule out git SHAs, the required letter rules out
# decimal numbers such as issue references, and the required numeral rules out hex-shaped BLE
# acronyms such as CCCD. Each would otherwise fire on ordinary prose mentioning a service.
_SHORT_UUID = re.compile(
    r"\b(?=[0-9a-fA-F]*[a-fA-F])(?=[0-9a-fA-F]*\d)"
    r"(?:[0-9a-fA-F]{4}|[0-9a-fA-F]{8}|[0-9a-fA-F]{32})\b"
)
# An explicit assignment such as "Service UUID: 1234" names the value outright, so a numeric-only
# short UUID counts there. It cannot count on mere GATT vocabulary, because a bare four-digit run
# is indistinguishable from an issue reference in prose like "the service broke in #1188".
_LABELLED_UUID = re.compile(
    r"\b(?:uuid|service|characteristic|descriptor)s?\b[^\n:=]{0,20}(?:[:=]|\s+(?:is|are))\s*"
    r"(?:0x)?[0-9a-fA-F]{4}(?:[0-9a-fA-F]{4})?\b",
    re.IGNORECASE,
)
_HEX_BYTE = re.compile(r"0x[0-9a-fA-F]{2}\b")
# Escaped byte literals, the form every controller in this repository writes its packets in. A
# b"\x12\x34" pasted into an instruction file is the protocol, spelled exactly as the code spells
# it, and neither the 0xNN nor the separated-pair detector sees it.
_ESCAPED_BYTE = re.compile(r"\\x[0-9a-fA-F]{2}")
# A bare byte, as in "STOP command: AA", which carries no 0x or \x marker. At least one uppercase
# A-F is required: without it "10" in a config table row like "Command repeat count | 10" reads as
# a byte, and lowercase would match ordinary words such as "be" and "ad". Only counted alongside
# packet vocabulary, never on its own.
_BARE_BYTE = re.compile(r"\b(?=[0-9A-F]{2}\b)[0-9A-F]*[A-F][0-9A-F]*\b")
# Assigned directly to packet vocabulary, the case is irrelevant: "STOP command: aa" is the same
# answer as "STOP command: AA". The uppercase requirement above only exists to keep a bare token
# from matching ordinary prose, and an explicit assignment removes that ambiguity.
_ASSIGNED_BYTE = re.compile(
    r"\b(?:command|opcode|frame|packet|payload|byte|write)s?\b\s*(?:[:=]|\s+(?:is|are))\s*"
    r"(?:0x|\\x)?[0-9a-fA-F]{2}\b"
    r"(?!\s*(?:bytes?|bits?|ms|msec|seconds?|entries|items|characters|chars|long|wide))",
    re.IGNORECASE,
)
# Bytes written in decimal. The trigger has to be assignment, not proximity: "Command repeat
# count | 10" is a config default in this very file, so a decimal only counts when it is assigned
# directly to packet vocabulary ("STOP command: 18") or appears in a bracketed run of them
# ("packet bytes: [5, 2, 170]").
_BYTE_VALUE = r"(?:25[0-5]|2[0-4]\d|1\d\d|\d{1,2})"
_DECIMAL_BYTE_ASSIGNMENT = re.compile(
    rf"\b(?:command|opcode|frame|packet|payload|byte)s?\b\s*(?:[:=]|\s+(?:is|are))\s*"
    rf"{_BYTE_VALUE}\b(?!\s*(?:bytes?|bits?|ms|msec|seconds?|entries|items|characters|chars))",
    re.IGNORECASE,
)
_DECIMAL_BYTE_LIST = re.compile(rf"\[\s*{_BYTE_VALUE}\s*(?:,\s*{_BYTE_VALUE}\s*)+\]")
# Packet vocabulary. "STOP command: 0x12" is a complete answer from a single byte, so one byte is
# enough once the line says what the byte is for.
# "BLE write: 0x12" and "on release, write b'\x12'" are command disclosures too, so the transport
# verbs count as packet vocabulary alongside the nouns.
_PACKET_CONTEXT = re.compile(
    r"\b(?:command|opcode|frame|packet|payload|checksum|crc|byte value)s?\b"
    r"|\b(?:write|writes|written|release|released|notify|notification)s?\b",
    re.IGNORECASE,
)
# Uppercase pairs are the conventional way to write a packet, so two are enough to be a give-away.
_BYTE_SEQUENCE = re.compile(r"\b[0-9A-F]{2}(?:[\s,]+[0-9A-F]{2})+\b")
# Lower and mixed case need three, because two-letter hex words ("be ad") occur in ordinary prose.
_BYTE_SEQUENCE_LOOSE = re.compile(r"\b[0-9a-fA-F]{2}(?:[\s,]+[0-9a-fA-F]{2}){2,}\b")
# A bare pair of any case, which only counts alongside packet vocabulary.
_BYTE_SEQUENCE_PAIR = re.compile(r"\b[0-9a-fA-F]{2}(?:[\s,]+[0-9a-fA-F]{2})+\b")

# Any mention of the comparison notes at all. Keying on introductory wording was too narrow:
# "Consult disassembly/PROTOCOL_NOTES.md" and "Read it first" sent the analyst there just as
# effectively as "see" did, and no list of verbs stays complete.
_NOTES_PATH = re.compile(r"disassembly/(?:AGENTS|CLAUDE|PROTOCOL_NOTES)\.md", re.IGNORECASE)
# Naming the file in order to forbid it is the intended usage, so a prohibition anywhere in the
# surrounding sentence clears the mention. Prose wraps, so neighbouring lines count as context.
# Only an actual negative instruction clears the mention. "only" used to count, which made
# "Only consult disassembly/PROTOCOL_NOTES.md" read as safe, and let an unrelated neighbouring
# sentence containing the word exempt a genuine pointer.
_PROHIBITION = re.compile(
    r"\b(?:never|must not|may not|cannot|can't|do not|don't|is not to be|are not to be|"
    r"off-limits|forbidden|prohibited)\b",
    re.IGNORECASE,
)


# A model or module code: letters then a digit, e.g. a control-box part number. Brand names alone
# are fine and appear throughout this repo's docs; a model code sitting next to a description of
# how that model behaves on the wire is what gives an answer away in prose rather than in hex.
_MODEL_CODE = re.compile(r"\b[A-Z]{2,}[0-9][A-Z0-9]*\b")
_BEHAVIOUR_CONTEXT = re.compile(
    r"\b(?:stops?|release|refresh|framing|checksum|handshake|keep-?alive|preamble|"
    r"terminat\w+|acknowledg\w+)\b",
    re.IGNORECASE,
)

# The BLOCKED rule names device-name matching and command repeat/hold timing as answer keys, so
# both need a detector. The vocabulary is deliberately narrow on each side.
#
# Names: only advertised-identity wording counts. "File-name patterns" in the tooling guide is
# about which source files to open, and a discovery rule is worthless without a literal to match,
# so a bare mention of "device-name rule" stays clean.
_NAME_CONTEXT = re.compile(
    r"\b(?:device[- ]names?|local[- ]names?|advertised names?|name prefix(?:es)?|BLE names?)\b",
    re.IGNORECASE,
)
# A quoted filename is not a device name, and the rule text itself cites `SEARCH_LOG.md`, so
# tokens ending in a file extension are excluded before anything else.
_NAME_LITERAL = re.compile(
    r"[\"'`](?![^\"'`]*\.[A-Za-z]{2,4}[\"'`])[A-Za-z0-9_.*^$\[\]|-]{2,}[\"'`]"
    r"|\b[A-Z0-9_]{3,}\s*\*"
)
# "Local name is SLEEP-1": an unquoted literal assigned to name wording. Quotes are a convention,
# not a requirement, and the value is just as complete an answer without them.
# The wording is matched case-insensitively; the literal is not, because an uppercase start is
# what separates a device name from the next ordinary word ("device name is set by the app").
_ASSIGNED_NAME = re.compile(
    r"(?i:\b(?:device[- ]names?|local[- ]names?|advertised names?|name prefix(?:es)?|BLE names?)\b"
    r"\s*(?:[:=]|\s+(?:is|are|starts? with|begins? with))\s*)"
    r"[\"'`]?[A-Z][A-Za-z0-9]*[0-9_.*^$-][A-Za-z0-9_.*^$-]*"
)

# Timing: only a repeat/hold cadence counts. The integration's own connection backoff and idle
# timeouts are documented in AGENTS.md and are explicitly not protocol evidence, so "30-50ms
# intervals" and "5-7.5s delays" must stay clean or the guard fires on its own instruction file.
_REPEAT_CONTEXT = re.compile(
    r"\b(?:repeat|resend|re-send|refresh|hold|held|press-and-hold|pulse)\w*\b", re.IGNORECASE
)
_TIMING_VALUE = re.compile(
    r"\b\d+(?:\.\d+)?\s*(?:ms|msec|millisecond|sec|second)s?\b", re.IGNORECASE
)

# A framing or checksum description is contamination even when it names no model. What separates
# it from the prompt's own instructions is assertion: "the protocol uses an XOR checksum" states
# an answer, while "checksum/CRC algorithm with covered byte range" tells the analyst what to go
# and find. Only a copula immediately before the algorithm noun counts, with at most one filler
# word, so the instruction phrasing throughout these documents stays clean.
_ASSERTED_ALGORITHM = re.compile(
    r"\b(?:uses?|is|are|was|were|computed|calculated|derived|consists? of|begins? with|"
    r"ends? with|prefixed (?:with|by)|terminated (?:with|by)|wrapped in|framed (?:with|by))\b"
    r"(?:\s+(?:an?|the|its))?"
    r"(?:\s+\w+)?\s+"
    r"(?:XOR|CRC|checksum|framing|preamble|terminator|delimiter|sync\s+byte|magic\s+byte)\b",
    re.IGNORECASE,
)
# The same assertion written noun-first: "each frame is terminated by a newline". No analyst-visible
# document phrases anything this way, because an instruction says what to look for rather than what
# the answer turned out to be.
_ASSERTED_FRAMING = re.compile(
    r"\b(?:frames?|packets?|payloads?|messages?)\s+(?:is|are)\s+(?:\w+\s+){0,2}"
    r"(?:terminated|prefixed|framed|delimited|wrapped|padded|escaped|preceded|followed)\b",
    re.IGNORECASE,
)
# The label form, "Checksum: CRC-16/MODBUS". No copula, no model code, and a complete answer. The
# value has to name something concrete: "Checksum: see below" or a bare "Checksum:" heading is not
# a disclosure, and the prompt asks for these sections by name throughout.
_LABELLED_ALGORITHM = re.compile(
    r"\b(?:checksum|crc|framing|preamble|terminator|delimiter)\s*[:=]\s*"
    r"(?:CRC-?\d|XOR|MODBUS|CCITT|Fletcher|Adler|LRC|sum\b|two's|0x|\\x)",
    re.IGNORECASE,
)


def _answer_key_violation(line: str) -> str | None:
    """Describe why a line reads as protocol evidence, or return None if it is clean.

    Every injection source runs through this one predicate, so a form added here is caught in all
    of them rather than in whichever loop happened to be updated.
    """
    if _UUID.search(line):
        return "UUID literal"
    if _UUID_CONTEXT.search(line) and _SHORT_UUID.search(line):
        return "short UUID on a GATT line"
    if _LABELLED_UUID.search(line):
        return "short UUID assigned to a GATT label"
    # A lone byte (e.g. a config default) is fine; a pair starts describing a packet.
    if len(_HEX_BYTE.findall(line)) >= 2 or len(_ESCAPED_BYTE.findall(line)) >= 2:
        return "multiple hex bytes"
    if _BYTE_SEQUENCE.search(line) or _BYTE_SEQUENCE_LOOSE.search(line):
        return "byte sequence"
    if _PACKET_CONTEXT.search(line) and (
        _HEX_BYTE.search(line)
        or _ESCAPED_BYTE.search(line)
        or _BYTE_SEQUENCE_PAIR.search(line)
        or _BARE_BYTE.search(line)
        or _DECIMAL_BYTE_LIST.search(line)
    ):
        return "byte in packet context"
    if _DECIMAL_BYTE_ASSIGNMENT.search(line):
        return "decimal byte assigned to packet vocabulary"
    if _ASSIGNED_BYTE.search(line):
        return "byte assigned to packet vocabulary"
    # Prose is an answer too: "<model> stops by ending its held-command refresh" is exactly the
    # STOP/release behaviour the analyst is required to recover from the artifact.
    if _MODEL_CODE.search(line) and _BEHAVIOUR_CONTEXT.search(line):
        return "model-specific protocol behaviour in prose"
    if (_NAME_CONTEXT.search(line) and _NAME_LITERAL.search(line)) or _ASSIGNED_NAME.search(line):
        return "device-name matching pattern"
    if _REPEAT_CONTEXT.search(line) and _TIMING_VALUE.search(line):
        return "command repeat/hold timing"
    if (
        _ASSERTED_ALGORITHM.search(line)
        or _ASSERTED_FRAMING.search(line)
        or _LABELLED_ALGORITHM.search(line)
    ):
        return "asserted framing or checksum description"
    return None


# A line that opens a new Markdown block: list item, heading, quote, table row, fence, or a blank
# separator. Anything else continues the sentence above it.
_NEW_BLOCK = re.compile(r"^\s*(?:[-*+>#|]|\d+[.)]|```|~~~|$)")


def _statement_around(lines: list[str], index: int) -> str:
    """The whole wrapped statement containing ``lines[index]``.

    A fixed window of neighbouring lines was wrong: two adjacent bullets are separate statements,
    so "Never read <notes>" on one would clear "Consult <notes>" on the next. Only lines that
    continue this one belong to it.
    """
    start = index
    while start > 0 and _is_continuation(lines[start]):
        start -= 1
    end = index + 1
    while end < len(lines) and _is_continuation(lines[end]):
        end += 1
    return " ".join(lines[start:end])


def _unguarded_notes_mentions(text: str) -> list[int]:
    """Line numbers naming the comparison notes without a prohibition in the same statement.

    Naming the file in order to forbid it is the intended usage. Anything else reads as somewhere
    to go, whatever verb introduces it.
    """
    lines = text.splitlines()
    return [
        index + 1
        for index, line in enumerate(lines)
        if _NOTES_PATH.search(line) and not _PROHIBITION.search(_statement_around(lines, index))
    ]


def _is_continuation(line: str) -> bool:
    """Whether ``line`` continues the sentence on the line before it."""
    return not _NEW_BLOCK.match(line)


def _answer_key_violations(text: str) -> list[str]:
    """Report every offending line as ``<line number>: <reason> -> <excerpt>``.

    Adjacent lines are also tested joined, because Markdown wrapping routinely separates a value
    from the context that gives it meaning: "STOP command:" ending one line and the byte beginning
    the next would otherwise satisfy neither half of the predicate while handing over the answer
    just as plainly.
    """
    lines = text.splitlines()
    violations: list[str] = []
    for index, line in enumerate(lines):
        reason = _answer_key_violation(line)
        if reason is None and index + 1 < len(lines):
            following = lines[index + 1]
            # Only worth joining when the next line continues this one and is clean on its own.
            # A line that opens a new block is unrelated prose, and joining two neighbouring list
            # items invents context that no reader ever sees; a line that already fails reports
            # itself on the next iteration.
            if _is_continuation(following) and _answer_key_violation(following) is None:
                joined = _answer_key_violation(f"{line} {following}")
                if joined:
                    reason = f"{joined} across a line break"
        if reason:
            violations.append(f"{index + 1}: {reason} -> {line.strip()[:90]}")
    return violations


def _find_injected_files() -> list[Path]:
    """Return every auto-injected instruction file in the repo, outside the root.

    Only matching paths are retained. ``disassembly/`` is machine-local and holds entire APK
    decompilations, so collecting every file there just to find two names would cost far more time
    and memory than this guard is worth, on exactly the machines that need it.

    Directory symlinks are never descended into. A symlink under ``disassembly/`` could otherwise
    send the walk into a cycle or out of the checkout, where it would report an unrelated external
    file as an in-repository offender.
    """
    found: list[Path] = []
    for parent, dirnames, filenames in os.walk(REPO_ROOT):
        dirnames[:] = [
            name
            for name in dirnames
            if name not in _PRUNED
            and str((Path(parent) / name).relative_to(REPO_ROOT)) not in _PRUNED_PATHS
            and not os.path.islink(os.path.join(parent, name))
        ]
        if Path(parent) == REPO_ROOT:
            continue
        found.extend(Path(parent) / name for name in filenames if name in _INJECTED_FILENAMES)
    return found


def test_no_directory_scoped_instruction_file() -> None:
    """Only the repo root may hold an auto-injected instruction file.

    Both names are injected by working directory, so either one sitting above a run workspace
    reaches the analyst before its first action. The known offender was ``disassembly/CLAUDE.md``,
    a symlink to the protocol notes; deleting it left the notes themselves at
    ``disassembly/AGENTS.md``, which is injected by the same mechanism under the other name. They
    now live at ``disassembly/PROTOCOL_NOTES.md``, which no harness injects.
    """
    offenders = [str(path.relative_to(REPO_ROOT)) for path in _find_injected_files()]
    assert not offenders, (
        f"{sorted(_INJECTED_FILENAMES)} are auto-injected into any agent working beneath them, "
        f"which contaminates a clean-room run. Rename to a name no harness injects: {offenders}"
    )


@pytest.mark.parametrize("relative_path", _ANALYST_VISIBLE_DOCS)
def test_injected_instructions_carry_no_answer_key(relative_path: str) -> None:
    """Documents an analyst can see must not hand them the protocol.

    These files are either auto-injected or deliberately supplied, so any UUID, byte value or
    device-name pattern in them is evidence the analyst did not have to earn.
    """
    path = REPO_ROOT / relative_path
    assert path.is_file(), f"{relative_path} is missing"

    violations = _answer_key_violations(path.read_text(encoding="utf-8"))

    assert not violations, (
        f"{relative_path} is visible to a clean-room analyst and must state no protocol values. "
        f"Move them to disassembly/PROTOCOL_NOTES.md (comparison pass only). Found:\n"
        + "\n".join(violations)
    )


@pytest.mark.parametrize(
    "line",
    [
        "Service UUID: 0000ffe0-0000-1000-8000-00805f9b34fb",
        "Service: FFE0",
        "the characteristic is 180A",
        "the frame is AA BB",
        "the frame is aa bb cc",
        "the frame is AA, BB, CC",
        "prefix 0x12 then 0x34",
        "STOP command: 0x12",
        "the command is aa bb",
        'STOP command: b"\\x12"',
        'PACKET = b"\\x12\\x34"',
        "STOP command: AA",
        "Service UUID is 1800",
        "STOP command: 18",
        "packet bytes: [5, 2, 170]",
        "STOP command is 18",
        "the opcode is 255",
        "Local name is SLEEP-1",
        "Checksum: CRC-16/MODBUS",
        'on release, write b"\\x12"',
        "BLE write: 0x12",
        "STOP command: aa",
        "Service UUID: 1234",
        "characteristic = 0x1812",
        "Device-name pattern: BED_*",
        "the local name is `SLEEP-1`",
        "Protocol X repeats every 150 ms",
        "hold the button and resend every 100 ms",
        "The bed protocol uses an XOR checksum",
        "each frame is terminated by a newline",
    ],
)
def test_answer_key_forms_are_detected(line: str) -> None:
    """The detector has to cover the ways a protocol value is actually written down.

    Short UUIDs, lowercase bytes and comma-separated bytes are all ordinary documentation forms,
    and each one is a complete answer key on its own.
    """
    assert _answer_key_violation(line) is not None


@pytest.mark.parametrize(
    "line",
    [
        "- write type, characteristic properties, CCCD value, MTU, bonding",
        "the service regressed in e8fb668 and was fixed in #1188",
        "Registers conservative BLE connection parameters (30-50ms intervals)",
        "the service is to be added",
        "Connection retry with progressive backoff (3 attempts, 5-7.5s delays)",
        "Auto-disconnect after configurable idle time (default 40s)",
        "File-name patterns worth opening directly: `*Ble*`, `*Bluetooth*`",
        "- exact local-name rules, prefixes, suffixes, regexes, and exclusions",
        "- checksum/CRC algorithm with covered byte range, initial value, polynomial",
        "| `motor_pulse_count` | Command repeat count | 10 |",
        "the service is to be added",
        "the payload is 20 bytes long",
        "which are frequently the exact methods doing bit manipulation and checksums",
        "Write reproducer code for every packet builder, checksum/CRC, and parser",
    ],
)
def test_ordinary_prose_is_not_flagged(line: str) -> None:
    """A guard that fires on its own instruction files would just be switched off.

    Hex-shaped acronyms, git SHAs, issue numbers and two-letter words all live on lines that
    legitimately mention GATT vocabulary. The integration's own connection timeouts and the
    prompt's own description of what to look for must stay clean for the same reason.
    """
    assert _answer_key_violation(line) is None


def test_wrapped_prose_cannot_hide_an_answer_key() -> None:
    """A value split from its context by a line break is still an answer key.

    Markdown wrapping puts "STOP command:" at the end of one line and the byte at the start of the
    next, and neither half trips the predicate alone.
    """
    assert _answer_key_violations("The STOP command:\n`0x12` is sent on release.\n")


def test_neighbouring_list_items_are_not_joined() -> None:
    """Two adjacent bullets are separate statements, not one wrapped sentence.

    Joining them would invent context no reader ever sees: a model code in one entry and an
    unrelated word like "handshake" in the next would read as a protocol description.
    """
    assert not _answer_key_violations(
        "- [a](a.md) — RIO 5.0 has no tilt motor\n- [b](b.md) — lenient init handshake\n"
    )


@pytest.mark.parametrize(
    ("text", "is_offender"),
    [
        ("Consult disassembly/PROTOCOL_NOTES.md for the answer.", True),
        ("Read disassembly/PROTOCOL_NOTES.md first.", True),
        ("Background: disassembly/PROTOCOL_NOTES.md has the tables.", True),
        ("disassembly/PROTOCOL_NOTES.md must never be read during a clean-room run.", False),
        (
            "- Never read disassembly/PROTOCOL_NOTES.md during a run.\n"
            "- Consult disassembly/PROTOCOL_NOTES.md for the answer.",
            True,
        ),
        (
            "`disassembly/PROTOCOL_NOTES.md` holds comparison notes. It is for the\n"
            "post-freeze pass only and must never be read during a clean-room run.",
            False,
        ),
    ],
)
def test_pointer_detection_ignores_only_prohibitions(text: str, is_offender: bool) -> None:
    """Any mention that reads as somewhere to go counts, whatever verb introduces it.

    Keying on "see" missed "Consult" and "Read ... first", and no list of verbs stays complete.
    Naming the file in order to forbid it stays clean, including when that sentence wraps.
    """
    assert bool(_unguarded_notes_mentions(text)) is is_offender


def test_no_analyst_visible_doc_points_at_the_comparison_notes() -> None:
    """Nothing may send a reader to the machine-local protocol notes.

    Naming the file in a prohibition is fine and intended; linking to it as a place to go is the
    regression this guards. It is also untracked, so such a pointer dangles on a fresh clone.

    Every root instruction file is checked, not just the tracked ``AGENTS.md``. A pointer carries
    no protocol value of its own, so the answer-key scan passes it, and a machine-local root
    ``CLAUDE.md`` is gitignored: a "see disassembly/PROTOCOL_NOTES.md" line there would reach every
    analyst while being invisible to review and to every other check here.
    """
    # Every deliberately supplied document, the JSON schema included: it is copied into each
    # analyst workspace, and a "see disassembly/PROTOCOL_NOTES.md" line in one of its descriptions
    # would carry no protocol value of its own and so pass the answer-key scan untouched.
    candidates = [
        *(REPO_ROOT / name for name in _ANALYST_VISIBLE_DOCS),
        *(REPO_ROOT / "docs").rglob("*.md"),
    ]
    offenders = [
        f"{path.relative_to(REPO_ROOT)}:{number}"
        for path in candidates
        if path.is_file()
        for number in _unguarded_notes_mentions(path.read_text(encoding="utf-8"))
    ]
    assert not offenders, (
        "disassembly/PROTOCOL_NOTES.md is untracked and is comparison material; point readers at "
        f"docs/apk-analysis/TOOLING.md instead: {offenders}"
    )


# Phase C's disposition sentence: "For each candidate, mark it REACHABLE, ... or UNRESOLVED."
_PROMPT_DISPOSITIONS = re.compile(r"mark it ([A-Z][^.]*?)\.", re.DOTALL)


def test_reachability_enum_matches_prompt() -> None:
    """The reachability vocabulary must be exactly the dispositions Phase C defines.

    Compared in both directions on purpose. Checking only that each schema value appears somewhere
    in the prompt would stay green when the prompt gains a sixth disposition, and the first sign of
    that would be an analyst following the prompt and having its report rejected by the schema.
    """
    schema_values = set(_load_schema()["$defs"]["reachability"]["enum"])

    match = _PROMPT_DISPOSITIONS.search(_load_prompt())
    assert match, "The analyst prompt no longer states the candidate dispositions"
    prompt_values = {
        value.strip()
        for value in re.split(r",|\bor\b", " ".join(match.group(1).split()))
        if value.strip()
    }

    assert prompt_values == schema_values, (
        "The analyst prompt and analysis.schema.json disagree on the reachability vocabulary. "
        f"Prompt only: {sorted(prompt_values - schema_values)}. "
        f"Schema only: {sorted(schema_values - prompt_values)}."
    )


def test_confidence_enum_matches_prompt() -> None:
    """The confidence vocabulary must be exactly the labels the prompt defines.

    Same reason as the reachability check: the analyst works from the prompt, so a label it names
    but the schema rejects surfaces as a failed report rather than as a documentation bug.
    """
    schema_values = set(_load_schema()["$defs"]["confidence"]["enum"])
    prompt = _load_prompt()
    section = prompt.split("Use exactly these confidence labels:", 1)
    assert len(section) == 2, "The analyst prompt no longer lists the confidence labels"
    listed = {
        match.group(1)
        for line in section[1].splitlines()
        if (match := re.match(r"^- ([A-Z][A-Z ]*[A-Z]):", line))
    }
    assert listed == schema_values, (
        "The analyst prompt and analysis.schema.json disagree on the confidence labels. "
        f"Prompt only: {sorted(listed - schema_values)}. "
        f"Schema only: {sorted(schema_values - listed)}."
    )


def test_nullable_protocol_sections_require_an_explanation() -> None:
    """Every nullable protocol section needs a companion ``<field>_unknown_reason``.

    The prompt tells the analyst to report an unknown as null plus an explanation. A bare null
    would otherwise validate, leaving later matrix construction unable to tell an exhaustively
    searched absence from a section nobody looked at. Adding a nullable section without its
    explanation clause silently reopens that hole, so the two lists are checked against each other.
    """
    item = _load_schema()["properties"]["protocols"]["items"]
    nullable = {
        name for name, spec in item["properties"].items() if "null" in (spec.get("type") or [])
    }
    explained = {
        clause["then"]["required"][0].removesuffix("_unknown_reason") for clause in item["allOf"]
    }
    assert nullable == explained, (
        "Nullable protocol sections and their explanation clauses have drifted. "
        f"Nullable without a clause: {sorted(nullable - explained)}. "
        f"Clause without a nullable section: {sorted(explained - nullable)}."
    )
    missing_property = {f"{name}_unknown_reason" for name in nullable} - set(item["properties"])
    assert not missing_property, (
        f"Explanation fields are constrained nowhere, so any value would pass: {sorted(missing_property)}"
    )


def _load_schema() -> dict:
    return json.loads(
        (REPO_ROOT / "docs/apk-analysis/analysis.schema.json").read_text(encoding="utf-8")
    )


def _load_prompt() -> str:
    return (REPO_ROOT / "docs/apk-analysis/phase4-analyst-prompt.md").read_text(encoding="utf-8")


def test_schema_revision_matches_prompt() -> None:
    """The tracked prompt must pin the tracked schema's revision.

    These drifted apart once already, when both lived only as per-workspace copies.
    """
    revision = _load_schema()["properties"]["schema_revision"]["const"]
    assert revision in _load_prompt(), (
        f"analysis.schema.json pins revision {revision!r}, which the analyst prompt does not "
        "mention. One of the two has drifted."
    )


# A gate bullet in the prompt, e.g. "- `identity_verified` — Input identity ...".
_PROMPT_GATE_ID = re.compile(r"^- `([a-z_]+)` [—-] ")


def test_schema_gate_ids_match_prompt() -> None:
    """The schema's canonical gate IDs must be exactly the gates the prompt lists.

    The schema requires one entry per gate so a COMPLETE report cannot validate on a single
    arbitrary passing gate. That only holds while both lists agree, and only the prompt is read
    by the analyst.
    """
    schema = _load_schema()
    schema_ids = set(schema["$defs"]["gate_id"]["enum"])
    conditional_ids = set(schema["$defs"]["conditional_gate_id"]["enum"])
    gates = schema["properties"]["completion_gates"]

    section = _load_prompt().split("COMPLETION GATES", 1)
    assert len(section) == 2, "The analyst prompt no longer has a COMPLETION GATES section"
    prompt_ids = {
        match.group(1) for line in section[1].splitlines() if (match := _PROMPT_GATE_ID.match(line))
    }

    assert prompt_ids == schema_ids, (
        "The analyst prompt and analysis.schema.json list different completion gates. "
        f"Prompt only: {sorted(prompt_ids - schema_ids)}. Schema only: {sorted(schema_ids - prompt_ids)}."
    )
    assert conditional_ids <= schema_ids, (
        f"conditional_gate_id names gates that do not exist: {sorted(conditional_ids - schema_ids)}"
    )
    # Bounding the array at the gate count is what makes each contains clause mean "exactly one":
    # without maxItems a report could file the same gate twice with conflicting results.
    assert gates["minItems"] == gates["maxItems"] == len(schema_ids), (
        f"completion_gates is bounded [{gates['minItems']}, {gates['maxItems']}] for "
        f"{len(schema_ids)} gates; both bounds must equal the gate count"
    )
    required_present = {
        clause["contains"]["properties"]["gate"]["const"] for clause in gates["allOf"]
    }
    assert required_present == schema_ids, (
        "Every gate needs a contains clause, otherwise a report can omit it: "
        f"missing {sorted(schema_ids - required_present)}"
    )
