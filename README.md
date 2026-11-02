<h1>
  <picture>
    <source media="(prefers-color-scheme: dark)" srcset="assets/logo-dark.svg">
    <img alt="Mintence" src="assets/logo-light.svg" width="360">
  </picture>
</h1>

[![License: MIT](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)
![Python 3.10+](https://img.shields.io/badge/python-3.10%2B-blue.svg)
![No dependencies](https://img.shields.io/badge/dependencies-none-blue.svg)

**An open-source sentence mining tool for English, right in your terminal.**

Words stick better when you remember where you found them. That is the idea behind sentence mining: you collect new words together with the sentences they came from. Mintence (*sentence* + *mining*) takes care of the dictionary part. Give it the sentence and the word, choose the sense that fits, and your entry is written:

```
(100)                                                     ← entry number
The police carried out a thorough investigation.          ← where you found the word
thorough adjective /ˈθʌɹə/ /ˈθʌɹoʊ/                       ← part of speech and pronunciation
Painstaking and careful not to miss or omit any detail.   ← the sense you chose
```

## Why Mintence

- **You choose the meaning.** A word can mean many things, and only you know what it meant in your sentence. Old and rare senses stay out of the way until you ask for them.
- **Your notes stay yours.** Entries go to a plain text file on your computer. There is no account, no API key and no subscription.
- **It handles real reading.** Words, phrasal verbs and idioms all work, and inflected forms lead to the base word (*heralded* → *herald*, *went* → *go*).
- **It is light.** One Python file with no dependencies. A word you have looked up before comes back instantly, even offline.
- **It is open.** The code is MIT-licensed, and the definitions come from [Wiktionary](https://en.wiktionary.org), a free dictionary written by volunteers.

## Installation

```
pipx install git+https://github.com/bsgustavoa/mintence
```

[pipx](https://pipx.pypa.io) installs the `mintence` command in its own environment. `pip install` with the same address also works. Update with `pipx upgrade mintence`; remove with `pipx uninstall mintence`.

## Quick start

**1.** Run `mintence`. The first time, it asks where to keep your files.

**2.** Paste your entries and press Enter twice:

```
The police carried out a thorough investigation.
thorough
```

**3.** Choose the part of speech, if there is more than one, and then the sense:

```
  1. thorough adjective
  2. thorough preposition (old or rare)
  3. thorough noun (old or rare)
Entry [1] (s = skip): 1

thorough adjective /ˈθʌɹə/ /ˈθʌɹoʊ/
  1. Painstaking and careful not to miss or omit any detail.
  2. Utter; complete; absolute.
Sense (number; s = skip): 1
```

**4.** Your entry is printed, and Mintence offers to add it to your mining file:

```
Append to mintence.txt? [Y/n]
```

## Input format

Paste the entries in the terminal, or save them to a file and run `mintence input.txt` (see [`example_input.txt`](example_input.txt)). Separate them with blank lines:

```
(100)

The police carried out a thorough investigation.
thorough

It took me a while to figure out how the program works.
figure out

embody
```

- **Sentence, then word:** the sentence on one line, the word or expression on the next.
- **Word alone:** Mintence shows the dictionary's examples, so you can use one as the sentence.
- **`(number)` at the top** (optional): the number of the first entry.
- **Lines starting with `# `** are comments.

## Choosing senses

| You type | Result |
|---|---|
| `2` | sense 2 |
| `2b` | sense 2, with example *b* as the sentence (for a word alone) |
| `a` | also show the old and rare senses |
| `s` | skip the word |

If a word is not found, you can type it again. Mintence also warns you when a block has more than two lines, which usually means a missing blank line.

**Repeated words.** Senses you have already mined are marked in the list, so you can pick another one. If you choose a marked sense, Mintence asks before adding it again:

```
thorough adjective /ˈθʌɹə/ /ˈθʌɹoʊ/
  1. Painstaking and careful not to miss or omit any detail.  [already mined: (100)]
  2. Utter; complete; absolute.
Sense (number; s = skip): 1
Already mined as (100). Add it again? [y/N]
```

Earlier entries that match no sense in the list, such as another part of speech, are shown above it for comparison.

## Your mining file

The first run asks for two things and remembers your answers:

1. **the folder for your files**, by default `~/mintence-files`;
2. **your main mining file**, by default `mintence.txt` in that folder. If you already keep a file in this format, give its path instead.

New entries continue the numbering of your mining file and, if you confirm, are added at its end. Existing entries are never changed. Each run also leaves a record such as `mintence_2026-11-01_1430_100-103.log` in your folder.

## Options

| Option | Description |
|---|---|
| `mintence FILE` | read the entries from `FILE` instead of the terminal |
| `-n N` | start the numbering at `N` |
| `-m FILE` | continue the numbering of `FILE`, for this run only (`FILE` is only read) |
| `-o FOLDER` | save this run's record in `FOLDER` |
| `--setup` | choose the folder and the main mining file again |
| `--clear-cache` | delete the saved dictionary data |
| `--version` | show the version |
| `-h` | show the help |

The first number of a run comes from, in order: `-n`, `-m`, `(number)` in the input, your main mining file. Entries are added to the main mining file only when their numbers continue its sequence.

## Good to know

- **Internet.** The first lookup of a word needs a connection, with at most one download per second. The word is then kept in `~/.cache/mintence` for 90 days.
- **Long lists** are done in rounds of 10. After each round, the entries are saved and Mintence asks whether to continue.
- **Stopping halfway.** Answer `n` or press Ctrl+C, and the entries already chosen are kept. The rest go to a file such as `input_remaining.txt`, and `mintence input_remaining.txt` picks up where you left off. Words that could not be downloaded go there too.
- **Definitions** are written by volunteers, so some are more technical than in a learner's dictionary, and a few words and expressions are missing, especially those with special characters (*a.m.*, *and/or*).
- Tested on Linux with Python 3.10, 3.11, 3.12 and 3.14.

## Contributing

Bug reports, ideas and pull requests are welcome in the [issues](https://github.com/bsgustavoa/mintence/issues).

## Credits and license

The code is under the [MIT license](LICENSE).

Definitions, examples and pronunciations come from [Wiktionary](https://en.wiktionary.org), by its contributors, under [CC BY-SA 4.0](https://creativecommons.org/licenses/by-sa/4.0/), through the data published by [Kaikki.org](https://kaikki.org) and [wiktextract](https://github.com/tatuylonen/wiktextract). Mintence shows them as published, apart from labels and formatting. If you share entries made with it, the same license applies to their definitions.
