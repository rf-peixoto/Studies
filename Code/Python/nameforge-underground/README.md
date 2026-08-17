# NameForge 2.0 — Underground Handle Workbench

This version is specialized for fictional Internet aliases rather than ordinary character names.

It models the fact that a handle can function as:

- a reputation marker
- an in-group signal
- a technical joke
- an aesthetic identity
- a deliberately mundane mask
- a literary/mythological reference
- an orthographic artifact
- a historical marker of Internet culture

## Requirements

Python 3.11+; standard library only.

## Quick start

```bash
python nameforge.py init my-underground-project
cd my-underground-project

python ../nameforge.py generate \
  --profile profiles/underground-character.json \
  --system profiles/underground-hacker-handle.json \
  --top 30 \
  --pool 1500 \
  --seed 1337 \
  --verbose
```

The generator is now archetype-driven rather than syllable-driven.

### Generate only one archetype

```bash
python ../nameforge.py generate \
  --profile profiles/underground-character.json \
  --system profiles/underground-hacker-handle.json \
  --archetype ironic \
  --top 20
```

Available archetypes:

- `technical`
- `abstract`
- `mythological`
- `scifi`
- `mundane`
- `threatening`
- `minimal`
- `compound`
- `technical_myth`
- `mundane_threat`
- `ironic`
- `orthographic`
- `leet`
- `numeric`
- `prefix`
- `suffix`

## Why this differs from a normal name generator

The old engine generated pronounceable names from phonological templates. That is useful for personal names, but it is a poor model of Internet handles.

The underground mode instead starts with semantic material:

```text
technical
abstract
mythology
science fiction
mundane occupations
threatening vocabulary
cyberpunk vocabulary
```

It then combines, truncates, mutates and transforms those words.

For example, a single seed may yield families such as:

```text
entropy
entropi
3ntropy
entrop
entropy13

deadlock
dead_lock
deadlock7

mildew
mild3w

null
null0
null_x
```

The objective is not historical reconstruction of a particular person's identity. It is to give a writer a controllable distribution of plausible fictional aliases.

## Scoring

The generator scores candidates using:

- scene fit
- authenticity
- memorability
- character resonance
- aesthetic fit
- interface usability
- uniqueness against the existing cast
- contradiction value
- old-school signal
- generic cyber/hacker penalty

The **authenticity** score intentionally penalizes obvious constructions such as `CyberWarrior` or `EliteHacker`. A technically sophisticated character does not necessarily need a technically obvious handle.

The **contradiction value** is particularly useful for fiction.

For example, an experienced underground operator called:

```text
mildew
```

can be more interesting than:

```text
DarkCyberPhantom
```

because the former tells the reader almost nothing while potentially becoming meaningful through reputation.

## Candidate files

`score` accepts one handle per line. You can optionally provide an archetype after a TAB:

```text
null	minimal
entropy	abstract
mildew	ironic
opcode	technical
janitor	mundane
deadlock	technical
```

Run:

```bash
python nameforge.py score \
  --profile profiles/underground-character.json \
  --system profiles/underground-hacker-handle.json \
  --names candidates.txt \
  --verbose
```

## Cast collision detection

Put character JSON files in `characters/`, each with an `aliases` array:

```json
{
  "id": "character-01",
  "given_name": "Elias",
  "family_name": "Voss",
  "aliases": ["null", "nullbyte"]
}
```

Then:

```bash
python nameforge.py cast-check characters/
```

The engine checks aliases against one another and reports high/moderate similarity.

## Important limitation

This is a heuristic creative tool. It does not determine whether a handle was historically used by a particular person, whether a term belongs to a particular subculture, or whether a reference is culturally appropriate.

For historical fiction, verify specific handles and slang against primary or period sources.

## Design philosophy

The intended workflow is:

```text
character
   ↓
social/Internet context
   ↓
handle archetypes
   ↓
semantic vocabulary
   ↓
compound / mutation / corruption
   ↓
candidate pool
   ↓
scoring
   ↓
cast collision analysis
   ↓
writer selection
```

The machine supplies possibilities and structured criticism. The writer makes the final choice.
