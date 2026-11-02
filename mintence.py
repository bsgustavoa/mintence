#!/usr/bin/env python3
# Mintence -- bsgustavoa (#dheg)
"""Mintence: open-source sentence mining for English, with data from Wiktionary.

Give it the sentence where you found a word, choose the sense that fits, and get
an entry with part of speech, pronunciations and definition.

Usage:
    mintence                            paste the entries in the terminal
    mintence input.txt                  read the entries from a file

Entries (same format in both cases), separated by blank lines:
    (100)                               optional: number of the first entry

    The police carried out a thorough investigation.
    thorough

    It took me a while to figure out how the program works.
    figure out

    embody                              a word alone: pick a dictionary example
"""
import argparse
import hashlib
import http.client
import json
import os
import re
import shutil
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

try:
    from importlib.metadata import version as _version
    VERSION = _version("mintence")
except Exception:
    VERSION = "dev"

SOURCE = "https://kaikki.org/dictionary/English/meaning/"
HEADERS = {"User-Agent": f"mintence/{VERSION} (https://github.com/bsgustavoa/mintence)"}
DELAY = 1.0      # seconds between requests
MAX_WORDS = 10   # words per round
CACHE_DAYS = 90  # how long a saved word stays fresh
CONFIG = Path(os.environ.get("XDG_CONFIG_HOME") or Path.home() / ".config") / "mintence" / "config.json"
CACHE = Path(os.environ.get("XDG_CACHE_HOME") or Path.home() / ".cache") / "mintence"
DEFAULT_OUTPUT = Path.home() / "mintence-files"

POS_NAMES = {"adj": "adjective", "adv": "adverb", "prep": "preposition", "conj": "conjunction",
             "pron": "pronoun", "intj": "exclamation", "det": "determiner", "num": "number",
             "article": "article", "particle": "particle", "contraction": "contraction",
             "name": "proper noun", "abbrev": "abbreviation"}
EXPRESSIONS = {"phrase", "prep_phrase", "proverb"}
NOT_WORDS = {"character", "symbol"}
GRAMMAR = ["countable", "uncountable", "transitive", "intransitive", "ambitransitive",
           "singular", "plural"]
LABELS = {"informal", "formal", "colloquial", "slang", "humorous", "derogatory", "offensive",
          "vulgar", "literary", "figuratively", "UK", "US", "Canada", "Australia", "Ireland",
          "New-Zealand", "India", "South-Africa", "Scotland", "Internet", "euphemistic", "obsolete", "archaic", "dated", "rare",
          "dialectal", "nonstandard", "historical", "uncommon", "poetic"}
HIDDEN = {"obsolete", "archaic", "dated", "rare", "dialectal", "nonstandard", "misspelling",
          "historical", "uncommon", "poetic", "no-gloss"}

POS_TAIL = re.compile(r"(?:,?\s+(?:%s))+$" % "|".join(sorted(
    set(POS_NAMES.values()) | {"noun", "verb", "phrasal verb", "modal verb", "auxiliary verb", "idiom"},
    key=len, reverse=True)))  # the part of speech at the end of a header
SPELLING_OF = re.compile(r"\bstandard spelling of ([^.,;]+)")  # colour -> color

_last_request = 0.0


@dataclass
class Sense:
    line: str               # "[grammar] (labels) definition"
    examples: list = field(default_factory=list)
    hidden: bool = False    # old or rare: shown only on request


@dataclass
class Entry:
    word: str
    pos: str                # empty for idioms
    header: str             # "word pos /BrE/ /NAmE/"
    senses: list = field(default_factory=list)


@dataclass
class Item:
    word: str
    context: str
    lines: list             # the block as typed, to warn about missing blank lines


def plural(n, one, many):
    return f"{n} {one if n == 1 else many}"


def read_text(path):
    try:
        return Path(path).read_text(encoding="utf-8-sig")  # also accepts a BOM
    except UnicodeDecodeError:
        sys.exit(f"mintence: {path} is not UTF-8 text; save it as UTF-8 and try again.")


# ---------------------------------------------------------------- dictionary

def download(word):
    """The word's data as text, or None if the dictionary does not have it."""
    global _last_request
    wait = DELAY - (time.time() - _last_request)
    if wait > 0:
        time.sleep(wait)
    q = urllib.parse.quote
    url = f"{SOURCE}{q(word[0], safe='')}/{q(word[:2], safe='')}/{q(word, safe='')}.jsonl"
    try:
        with urllib.request.urlopen(urllib.request.Request(url, headers=HEADERS), timeout=25) as r:
            return r.read().decode("utf-8")
    except urllib.error.HTTPError as e:
        if e.code == 404:
            return None
        raise
    finally:
        _last_request = time.time()


def parse_rows(text):
    return [json.loads(line) for line in text.splitlines() if line.strip()]


def rows_for(word):
    """All the data about a word, from the cache when it is still fresh."""
    name = hashlib.sha1(word.encode("utf-8")).hexdigest()  # safe on any file system
    path = CACHE / f"{name}.jsonl"
    old = None
    if path.is_file():
        try:
            old = parse_rows(path.read_text(encoding="utf-8"))
        except ValueError:
            old = None  # a damaged copy: download it again
        if old is not None and time.time() - path.stat().st_mtime < CACHE_DAYS * 86400:
            return old
    try:
        text = download(word)
    except (OSError, http.client.HTTPException):
        if old is None:
            raise
        return old  # offline: an old copy is better than none
    if text is None:
        return []
    rows = parse_rows(text)
    try:
        CACHE.mkdir(parents=True, exist_ok=True)
        temp = path.with_suffix(".tmp")
        temp.write_text(text, encoding="utf-8")
        temp.replace(path)
    except OSError:
        pass  # the cache is only a convenience
    return rows


def pronunciations(rows):
    """British and American pronunciations, or the first one given."""
    british = american = other = None
    for row in rows:
        for sound in row.get("sounds", []):
            ipa, tags = sound.get("ipa", ""), set(sound.get("tags", []))
            if not ipa.startswith("/"):
                continue
            other = other or ipa
            if tags & {"Received-Pronunciation", "UK", "British", "England"}:
                british = british or ipa
            if tags & {"General-American", "US", "GenAm"}:
                american = american or ipa
    found = [p for p in (british, american) if p]
    found = list(dict.fromkeys(found)) or ([other] if other else [])
    return " ".join(found)


def sense_line(sense):
    tags = sense.get("tags", [])
    grammar = [t for t in GRAMMAR if t in tags]
    labels = ["figurative" if t == "figuratively" else t.replace("-", " ") for t in tags if t in LABELS]
    parts = [f"[{', '.join(grammar)}]" if grammar else "",
             f"({', '.join(labels)})" if labels else "",
             " ".join(sense["glosses"][-1].split())]
    return " ".join(p for p in parts if p)


def examples_of(sense):
    """Short invented examples: long or old quotations do not help a learner."""
    out = []
    for x in sense.get("examples", []):
        text = " ".join(x.get("text", "").split())
        if text and x.get("type") != "quotation" and not x.get("ref") and len(text) <= 160 and "ſ" not in text:
            out.append(text)
    return out[:3]


def row_kind(row):
    """The part of speech as shown in an entry; empty for idioms."""
    multiword = " " in row.get("word", "")
    pos = row.get("pos", "")
    categories = str(row.get("categories", ""))
    if pos == "verb" and "English phrasal verbs" in categories:
        return "phrasal verb"
    if multiword and (pos in EXPRESSIONS or pos == "verb" or "English idioms" in categories):
        return ""
    return POS_NAMES.get(pos, pos)


def build_entries(rows):
    """One entry per part of speech, keeping every sense."""
    groups = {}
    for row in rows:
        if row.get("pos") in NOT_WORDS or not row.get("senses"):
            continue
        groups.setdefault((row.get("word", ""), row_kind(row)), []).append(row)
    entries = []
    for (word, kind), group in groups.items():
        senses, seen = [], set()
        for row in group:
            for s in row["senses"]:
                if not s.get("glosses") or s.get("form_of") or s.get("alt_of"):
                    continue
                if s["glosses"][-1].startswith("Used other than") or SPELLING_OF.search(s["glosses"][-1]):
                    continue  # "see strike, gold" and "standard spelling of color" define nothing
                line = sense_line(s)
                if line not in seen:
                    seen.add(line)
                    senses.append(Sense(line, examples_of(s), bool(HIDDEN & set(s.get("tags", [])))))
        if senses:
            sounds = "" if kind == "phrasal verb" or (not kind and " " in word) else pronunciations(group)
            header = " ".join(x for x in (word, kind, sounds) if x)
            entries.append(Entry(word, kind, header, senses))
    return entries


def base_words(rows, inflections_only=False):
    """Words this one is a form or spelling of: went -> go, colour -> color.
    Old forms count only if there is nothing else. A word with its own senses
    leads only to the words it inflects (saw -> see, but not be -> by)."""
    current, old = [], []
    for row in rows:
        for s in row.get("senses", []):
            target = old if HIDDEN & set(s.get("tags", [])) else current
            refs = [r.get("word") for r in s.get("form_of", [])]
            if not inflections_only:
                refs += [r.get("word") for r in s.get("alt_of", [])]
                refs += SPELLING_OF.findall(s["glosses"][-1]) if s.get("glosses") else []
            for ref in refs:
                if ref and ref not in target:
                    target.append(ref)
    return current or old


def clean_query(query):
    """The word as typed, without quotes and punctuation copied along with it."""
    word = " ".join(query.replace("’", "'").split()).strip(" \"“”,;:!?")
    if word.endswith(".") and "." not in word[:-1]:
        word = word[:-1]
    return word


def rows_any_case(word):
    rows = rows_for(word) if word != word.lower() else []
    rows += rows_for(word.lower())
    if not rows:
        for other in dict.fromkeys((word.capitalize(), word.title())):
            if other != word and other != word.lower():
                rows = rows_for(other)
                if rows:
                    break
    return rows


def lookup(query):
    """Entries for a word or expression, however it was capitalized."""
    word = clean_query(query)
    if not word:
        return []
    rows = rows_any_case(word)
    first, _, rest = word.partition(" ")
    if not rows and rest and first.lower() in ("a", "an", "the", "to"):
        rows = rows_any_case(rest)  # a piece of cake -> piece of cake
    if any(r.get("pos") != "name" for r in rows):
        rows = [r for r in rows if r.get("pos") != "name"]  # surnames and places named like the word
    entries = build_entries(rows)
    own_senses = any(not s.hidden for e in entries for s in e.senses)
    forms = []
    for base in base_words(rows, inflections_only=own_senses)[:2]:
        forms += [e for e in build_entries(rows_for(base)) if e.header not in {f.header for f in forms}]
    # ingrained: the adjective, then the verb ingrain; went: only go
    entries = entries + forms if own_senses else forms or entries
    return sorted(entries, key=lambda e: all(s.hidden for s in e.senses))  # old-only entries last


# ---------------------------------------------------------------- prompts

def ask(prompt):
    try:
        return input(prompt).strip()
    except EOFError:
        raise KeyboardInterrupt


def yes(prompt):
    return ask(prompt + " [Y/n] ").lower() in ("", "y", "yes")


def pick_number(prompt, n, default=None):
    """Ask for a number from 1 to n; return it, or None for 's' (skip)."""
    while True:
        a = ask(prompt).lower() or (str(default) if default else "")
        if a == "s":
            return None
        if a.isdecimal() and 1 <= int(a) <= n:
            return int(a)
        print(f"  type a number from 1 to {n}, or s to skip")


def find_entries(word):
    """Look the word up; if it is not found, let the user type it again.
    Connection problems reach the caller, which keeps the word for later."""
    while True:
        entries = lookup(word)
        if entries:
            return entries
        print(f"  “{word}” not found. Check the spelling.")
        word = ask("Type it again (Enter = skip): ")
        if not word:
            return []


def choose_entry(entries):
    if len(entries) == 1:
        return entries[0]
    for i, e in enumerate(entries, 1):
        old = "" if any(not s.hidden for s in e.senses) else " (old or rare)"
        print(f"  {i}. {e.word} {e.pos}".rstrip() + old)
    i = pick_number("Entry [1] (s = skip): ", len(entries), default=1)
    return entries[i - 1] if i else None


def shown_senses(entry):
    """Old and rare senses stay hidden until asked for, unless they are all the word has."""
    return [s for s in entry.senses if not s.hidden] or entry.senses


def marked(sense, prior):
    nums = [n for n, definition in prior if definition == sense.line]
    return f"{sense.line}  [already mined: {listing(nums)}]" if nums else sense.line


def add_again(sense, prior):
    """Ask before repeating a sense that is already mined; other senses need no question."""
    nums = [n for n, definition in prior if definition == sense.line]
    if not nums:
        return True
    return ask(f"Already mined as {listing(nums)}. Add it again? [y/N] ").lower() in ("y", "yes")


def show_senses(senses, context, prior=()):
    for i, s in enumerate(senses, 1):
        print(f"  {i}. {marked(s, prior)}")
        if not context:
            for j, x in enumerate(s.examples):
                print(f"       {chr(97 + j)}) {x}")


def choose_sense(entry, context, prior=()):
    """Return (sense, sentence), or None to skip. prior: [(number, definition)]
    of this word in the mining file."""
    print(f"\n{entry.header}")
    senses = shown_senses(entry)
    extra = len(entry.senses) - len(senses)
    if context and len(senses) == 1 and not extra:
        print(f"  {marked(senses[0], prior)}")
        return (senses[0], context) if add_again(senses[0], prior) else None
    show_senses(senses, context, prior)
    while True:
        more = f"; a = show {extra} old or rare" if extra else ""
        hint = "number" if context else "number + example letter, e.g. 1a"
        a = ask(f"Sense ({hint}; s = skip{more}): ").lower()
        if a == "s":
            return None
        if a == "a" and extra:
            senses, extra = entry.senses, 0
            show_senses(senses, context, prior)
            continue
        m = re.fullmatch(r"(\d+)([a-z]?)", a)
        n = len(senses)
        if not m or not 1 <= int(m[1]) <= n:
            print(f"  type a number from 1 to {n}" + ("" if context else ", optionally with a letter")
                  + ", or s to skip")
            continue
        sense = senses[int(m[1]) - 1]
        j = ord(m[2]) - 97 if m[2] and not context else None
        if j is not None and j >= len(sense.examples):
            print(f"  sense {m[1]} has {plural(len(sense.examples), 'example', 'examples')}")
            continue
        if not add_again(sense, prior):
            return None
        if context:
            return sense, context
        return sense, sense.examples[j] if j is not None else ask_sentence(sense)


def ask_sentence(sense):
    """A context sentence typed by the user; Enter uses the first example."""
    if sense.examples:
        return ask("Context sentence (Enter = example a): ") or sense.examples[0]
    while True:
        s = ask("Context sentence (this sense has no examples): ")
        if s:
            return s


def check_block(item):
    """A block with more than two lines usually means a missing blank line."""
    if len(item.lines) <= 2:
        return item
    print("  this entry has more than two lines (a missing blank line?):")
    for line in item.lines:
        print(f"    | {line}")
    print(f"  as one entry, the word is “{item.word}” and the lines above are its sentence.")
    if yes("  Keep it as one entry?"):
        return item
    print("  left for you to fix (listed at the end)")
    return None


# ---------------------------------------------------------------- input

def parse_entries(lines):
    """Parse blocks separated by blank lines.

    A block is "sentence / word" (two lines) or just "word" (one line);
    an optional "(number)" at the very top sets the first entry number.
    Lines starting with "# " are comments.
    Return (first_number or None, [Item, ...]).
    """
    start, items, block = None, [], []
    for raw in list(lines) + [""]:
        line = raw.strip()
        if line == "#" or line.startswith("# "):
            continue
        if line:
            block.append(line)
            continue
        if not block:
            continue
        m = re.fullmatch(r"\((\d+)\)", block[0])
        if m and start is None and not items:
            start = int(m[1])
            block = block[1:]
        if block:
            # the last line is the word; anything above it is the sentence
            items.append(Item(block[-1], " ".join(block[:-1]), block))
        block = []
    return start, items


def read_terminal():
    print("Paste your entries, separated by blank lines:")
    print("  - the sentence, then the word or expression on the next line;")
    print("  - or just the word, to pick an example from the dictionary.")
    print("Optional: put (number) on the first line to set the first entry number,")
    print("e.g. (100). Press Enter twice when done.\n")
    lines, blanks = [], 0
    while blanks < 2:
        try:
            line = input()
        except EOFError:
            break
        if line.strip():
            blanks = 0
        elif lines:
            blanks += 1
        lines.append(line)
    return parse_entries(lines)


# ---------------------------------------------------------------- settings

def load_config():
    try:
        config = json.loads(CONFIG.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return config if isinstance(config, dict) else None


def setup():
    """Ask where to save files and which main mining file to use; store the answers."""
    print("Mintence setup (run 'mintence --setup' to change it later)\n")
    output = ask(f"Folder to save your files [{DEFAULT_OUTPUT}]: ") or str(DEFAULT_OUTPUT)
    output = Path(output).expanduser().resolve()
    default = output / "mintence.txt"
    while True:
        answer = ask(f"Your main mining file [{default}]: ")
        mining = Path(answer).expanduser().resolve() if answer else default
        if mining.is_file():
            break
        if mining.is_dir():
            print(f"  {mining} is a folder; give the path of a file")
            continue
        if answer and not yes(f"  {mining} does not exist. Create it?"):
            continue
        try:
            mining.parent.mkdir(parents=True, exist_ok=True)
            mining.touch()
        except OSError as e:
            print(f"  could not create it: {e}")
            continue
        print(f"  created {mining}")
        break
    config = {"output": str(output), "mining": str(mining)}
    CONFIG.parent.mkdir(parents=True, exist_ok=True)
    CONFIG.write_text(json.dumps(config, indent=2) + "\n", encoding="utf-8")
    print(f"\nSaved to {CONFIG}\n")
    return config


# ---------------------------------------------------------------- mining file

def last_number(mining):
    nums = re.findall(r"^\((\d+)\)[ \t]*$", read_text(mining), re.M)  # not "(1999) was a year"
    return int(nums[-1]) if nums else 0


def header_word(header):
    """The word in an entry's header: "thorough adjective /ˈθʌɹə/" -> "thorough".
    Expressions stay whole, so "break the ice" does not count as "break"."""
    head = re.split(r"\s+/", header.strip())[0].rstrip(" ,")
    return POS_TAIL.sub("", head).casefold()


def mined_words(mining):
    """{word: [(entry number, definition)]} for the entries in the mining file."""
    found = {}
    if mining and Path(mining).is_file():
        pattern = r"^\((\d+)\)[ \t]*\n[^\n]*\n([^\n]*)\n?([^\n]*)"
        for num, header, definition in re.findall(pattern, read_text(mining), re.M):
            found.setdefault(header_word(header), []).append((num, definition.strip()))
    return found


def listing(nums):
    where = ", ".join(f"({n})" for n in nums[:3])
    return where + (f" and {len(nums) - 3} more" if len(nums) > 3 else "")


def mined_before(entry, mined):
    """This word's earlier entries. Those that match no sense on the list (another
    part of speech, another source) are shown here, so they can be compared."""
    prior = [m for key in {entry.word.casefold(), header_word(entry.header)}
             for m in mined.get(key, [])]
    shown = {s.line for s in shown_senses(entry)}
    others = [m for m in prior if m[1] not in shown]
    if others:
        print(f"  note: “{entry.word}” is already mined:")
        for num, definition in others[:3]:
            print(f"    ({num}) {definition}")
        if len(others) > 3:
            print(f"    and {len(others) - 3} more")
    return prior


def start_number(args, config, from_input=None):
    """-n, then -m, then (number) in the input, then the saved mining file, then ask."""
    if args.start is not None:
        return args.start
    if args.mining:
        return last_number(args.mining) + 1
    if from_input is not None:
        return from_input
    mining = config.get("mining")
    if mining and Path(mining).is_file():
        return last_number(mining) + 1
    if mining:
        print(f"Saved mining file not found: {mining} (run 'mintence --setup' to change it)")
    while True:
        a = ask("First number [1]: ") or "1"
        if a.isdecimal() and int(a) > 0:
            return int(a)
        print("  type a whole number, 1 or more")


def save_log(blocks, start, folder):
    folder = Path(folder).expanduser()
    folder.mkdir(parents=True, exist_ok=True)
    end = start + len(blocks) - 1
    name = f"mintence_{datetime.now():%Y-%m-%d_%H%M}_{start}-{end}"
    out = folder / f"{name}.log"
    k = 2
    while out.exists():  # never overwrite
        out = folder / f"{name}_{k}.log"
        k += 1
    out.write_text("\n".join(blocks), encoding="utf-8")
    return out


def append_to_mining(blocks, start, mining):
    """Offer to append the new entries to the main mining file (append only)."""
    path = Path(mining)
    expected = last_number(path) + 1
    if start != expected:
        print(f"Not added to {path.name}: these entries start at {start}, "
              f"but the next number there is {expected}.")
        return
    try:
        ok = yes(f"Append to {path.name}?")
    except KeyboardInterrupt:
        ok = False
    if not ok:
        print(f"Not added to {path.name}.")
        return
    text = read_text(path)
    trailing = len(text) - len(text.rstrip("\n"))
    sep = "\n" * max(0, 2 - trailing) if text.strip() else ""  # one blank line between entries
    try:
        with path.open("a", encoding="utf-8") as f:
            f.write(sep + "\n".join(blocks))
    except OSError as e:
        print(f"Could not add to {path}: {e}")
        return
    print(f"Added to {path}")


# ---------------------------------------------------------------- main

def run_round(batch, start, mined, offset, total):
    """Process one round of entries.
    Return (blocks, skipped, to_fix, later, done, interrupted); done = items handled."""
    blocks, skipped, to_fix, later = [], [], [], []
    for i, item in enumerate(batch):
        try:
            print(f"\n[{offset + i + 1}/{total}] {item.word}")
            if item.context:
                print(f"  “{item.context}”")
            if not check_block(item):
                to_fix.append(item)
                continue
            try:
                entries = find_entries(item.word)
            except (OSError, ValueError, http.client.HTTPException) as e:
                print(f"  could not reach the dictionary ({e}); left for later")
                later.append(item)
                continue
            entry = choose_entry(entries) if entries else None
            if entry is None:
                skipped.append(item.word)
                continue
            picked = choose_sense(entry, item.context, mined_before(entry, mined))
            if not picked:
                skipped.append(item.word)
                continue
        except KeyboardInterrupt:
            print("\nInterrupted; keeping the entries already chosen.")
            return blocks, skipped, to_fix, later, i, True
        sense, sentence = picked
        number = start + len(blocks)
        blocks.append(f"({number})\n{sentence}\n{entry.header}\n{sense.line}\n")
        mined.setdefault(header_word(entry.header), []).append((str(number), sense.line))
    return blocks, skipped, to_fix, later, len(batch), False


def finish_round(blocks, start, args, config):
    """Print the round's entries, save its log and offer to append them."""
    if not blocks:
        return
    print("\n" + "-" * 60 + "\n")
    print("\n".join(blocks))
    print("-" * 60)
    folder = args.output or config.get("output") or "."
    try:
        print(f"{plural(len(blocks), 'entry', 'entries')} saved to {save_log(blocks, start, folder)}")
    except OSError as e:
        print(f"Could not save the record in {folder}: {e}")
    main_file = config.get("mining")
    if main_file and not args.mining and Path(main_file).is_file():
        append_to_mining(blocks, start, main_file)


def save_remaining(to_fix, remaining, next_number, args, config):
    """Write the entries still to do to a file in the input format; return its path."""
    if args.input:
        source = Path(args.input).resolve()
        stem = re.sub(r"_remaining(_\d+)?$", "", source.stem)
        target = source.with_name(f"{stem}_remaining.txt")
    else:
        source = None
        folder = Path(args.output or config.get("output") or ".").expanduser()
        folder.mkdir(parents=True, exist_ok=True)
        target = folder / f"mintence_{datetime.now():%Y-%m-%d_%H%M}_remaining.txt"
    base, k = target, 2
    while target.exists() and target.resolve() != source:  # never overwrite other files
        target = base.with_name(f"{base.stem}_{k}.txt")
        k += 1
    parts = [f"({next_number})"] if next_number else []
    parts += ["# check: more than two lines (a missing blank line?)\n" + "\n".join(i.lines)
              for i in to_fix]
    parts += ["\n".join(i.lines) for i in remaining]
    target.write_text("\n\n".join(parts) + "\n", encoding="utf-8")
    return target


def banner():
    """One line at the start of a run: "Mint" in purple only in a real terminal."""
    color = (sys.stdout.isatty() and not os.environ.get("NO_COLOR")
             and os.environ.get("TERM") != "dumb"
             and (os.name != "nt" or "WT_SESSION" in os.environ))
    name = "\033[1;38;5;99mMint\033[0mence" if color else "Mintence"
    print(f"{name} {VERSION} · sentence mining for English\n")


def positive(value):
    if not value.isdecimal() or int(value) < 1:
        raise argparse.ArgumentTypeError("must be a whole number, 1 or more")
    return int(value)


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 epilog="Definitions: Wiktionary (CC BY-SA), through kaikki.org.",
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("input", nargs="?",
                    help="file with the entries (without it, paste them in the terminal)")
    numbering = ap.add_mutually_exclusive_group()
    numbering.add_argument("-n", "--start", type=positive, metavar="N",
                           help="number of the first entry")
    numbering.add_argument("-m", "--mining", metavar="FILE",
                           help="continue the numbering of this file (read only, this run only)")
    ap.add_argument("-o", "--output", metavar="FOLDER",
                    help="folder for the run log (this run only)")
    ap.add_argument("--setup", action="store_true",
                    help="choose again the output folder and the main mining file")
    ap.add_argument("--clear-cache", action="store_true",
                    help="delete the saved dictionary data (your mining files are not touched)")
    ap.add_argument("--version", action="version", version=f"mintence {VERSION}")
    args = ap.parse_args()
    for stream in (sys.stdout, sys.stderr):  # a terminal without UTF-8 must not stop the program
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(errors="replace")

    for path in (args.input, args.mining):
        if path and not Path(path).is_file():
            ap.error(f"file not found: {path}")

    if args.clear_cache:
        shutil.rmtree(CACHE, ignore_errors=True)
        print("Saved dictionary data deleted.")
        return

    banner()
    try:
        config = load_config()
        if args.setup:
            setup()
            return
        if config is None:
            config = setup()
        given_start, items = parse_entries(read_text(args.input).splitlines()) \
            if args.input else read_terminal()
        if not items:
            print("No words.")
            return
        start = start_number(args, config, given_start)
        print(f"\n{plural(len(items), 'entry', 'entries')} read; numbering starts at {start}.")
        if len(items) > MAX_WORDS:
            print(f"They will be done in rounds of {MAX_WORDS}.")
    except KeyboardInterrupt:
        print("\nInterrupted.")
        return

    # numbering that does not come from a mining file must be carried over
    # to the file of remaining entries
    keep_number = args.start is not None or given_start is not None or (
        not args.mining and not Path(config.get("mining") or "").is_file())
    mining = args.mining or config.get("mining")
    mined = mined_words(mining)  # entries chosen during this run are added to it
    pos, number, skipped, to_fix, later = 0, start, [], [], []
    while pos < len(items):
        blocks, sk, fix, lat, done, interrupted = run_round(
            items[pos:pos + MAX_WORDS], number, mined, pos, len(items))
        pos += done
        skipped += sk
        to_fix += fix
        later += lat
        finish_round(blocks, number, args, config)
        number += len(blocks)
        if interrupted or pos >= len(items):
            break
        nxt = min(MAX_WORDS, len(items) - pos)
        try:
            if not yes(f"\n{pos} of {len(items)} done. Continue with the next {nxt}?"):
                break
        except KeyboardInterrupt:
            break

    if skipped:
        print("\nSkipped: " + ", ".join(skipped))
    remaining = later + items[pos:]
    if remaining or to_fix:
        try:
            path = save_remaining(to_fix, remaining, number if keep_number else None, args, config)
        except OSError as e:
            print(f"\nCould not save the entries left for later: {e}")
            return
        print(f"\n{plural(len(remaining) + len(to_fix), 'entry', 'entries')} left for later, "
              f"saved to {path}")
        if to_fix:
            print(f"({len(to_fix)} marked “# check”: fix the blank lines before running it)")
        print(f"Continue with: mintence {path}")
    elif args.input and re.search(r"_remaining(_\d+)?$", Path(args.input).stem):
        Path(args.input).unlink()  # a file Mintence created, now fully done
        print(f"\nAll done; removed {args.input}")


if __name__ == "__main__":
    main()
