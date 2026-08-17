# NameForge 2.1 — Underground Handle Workbench

A workbench for inventing fictional Internet aliases for novel characters, rather than ordinary personal names.

It models the fact that a handle can function as:

- a reputation marker
- an in-group signal
- a technical joke
- an aesthetic identity
- a deliberately mundane mask
- a literary or mythological reference
- an orthographic artifact
- a historical marker of Internet culture

**2.1 is a bug-fix and enrichment release.** See `CHANGELOG.md` for the full list of what was broken in 2.0 and what changed.

## Requirements

Python 3.11+; standard library only.

## Quick start

```bash
python nameforge.py init my-underground-project
cd my-underground-project

python ../nameforge.py generate \
  --profile profiles/underground-character.json \
  --system profiles/underground-hacker-handle.json \
  --cast characters \
  --top 30 --pool 800 --seed 1337 --per-archetype 3 --verbose
```

`init` copies the shipped lexicon and the example cast into a new project directory.

## The workflow

```text
character profile → period + archetype selection → semantic vocabulary
       → compound / mutation / corruption → candidate pool
       → scoring → cast collision analysis → writer selection
```

The machine supplies possibilities and structured criticism. The writer makes the final choice.

## Commands

| Command | Purpose |
| --- | --- |
| `init` | Create a project directory from the shipped templates. |
| `generate` | Synthesize, mutate and rank handles for one character. |
| `score` | Rank handles *you* wrote, using the same criteria. |
| `analyze` | Inspect one handle: length, entropy, speakability, variants, recognised vocabulary. |
| `cast-check` | Find aliases that are too similar across your cast. |
| `system` | Summarise a handle system: archetypes, pool sizes, limits. |
| `doctor` | Validate a system file and report data-quality problems. |
| `export` | Snapshot a character plus its handle system into one file. |

## Archetypes

`technical` `abstract` `mythological` `scifi` `mundane` `threatening` `minimal` `compound` `technical_myth` `mundane_threat` `ironic` `orthographic` `leet` `numeric` `prefix` `suffix` `acronym` `phonetic` `seeded`

Generate a single archetype with `--archetype ironic`. Every archetype carries a period range, a tag set and an explanatory note, all defined once in `ARCHETYPES` inside `nameforge.py`.

Because one archetype can dominate a shortlist when a profile leans hard in its direction, `--per-archetype 3` caps how many results any single archetype may occupy. The tool prints a hint when it notices the imbalance.

## The lexicon

Vocabulary lives in the system JSON. Every term is an object:

```json
{
  "term": "bitrot",
  "tags": ["technical", "organic", "abstract"],
  "gloss": "data decaying quietly where nobody looks",
  "since": 1985,
  "weight": 1.3,
  "register": "insider"
}
```

| Field | Effect |
| --- | --- |
| `tags` | Matched against the character's `desired_impression`, `personality` and `interests` to produce the resonance score. |
| `gloss` | Printed beside every candidate, so you can see what the handle *means* without looking anything up. |
| `since` / `until` | Period plausibility. A 2011 character who picks `bluebox` gets a warning. |
| `weight` | Relative pick probability within its pool. |
| `register` | `insider` earns an authenticity bonus; `pop` takes a small penalty. |

Plain strings are still accepted, so 2.0 system files load without edits — they simply inherit their pool's default tags and no gloss.

Eleven pools ship by default: `technical`, `crypto`, `abstract`, `mythology`, `scifi`, `cyberpunk`, `phreak`, `mundane`, `bureaucratic`, `organic`, `threatening` — 270 glossed terms in total.

Run `python nameforge.py doctor --system <file>` after editing. It reports duplicates, cross-pool collisions, terms that can never pass validation, vocabulary that overlaps your own `overused` list, and archetypes that your vocabulary cannot actually build.

## Character profiles

Beyond the usual biography, these fields drive the score:

| Field | Effect |
| --- | --- |
| `desired_impression`, `personality`, `interests` | The tag set candidates are matched against. |
| `first_online_year` (or `era`) | Period plausibility for both archetypes and vocabulary. |
| `contradiction` | Raises the value of ironic and mundane handles; lowers overtly threatening ones. |
| `handle_history` | Earlier aliases. Echoes are rewarded as continuity; other characters' are penalised as collisions. |
| `avoid` | Substrings this character must never use. |
| `seed_words` | Your own vocabulary — surnames, places, private jokes — fed into the `seeded` archetype. |

Five example characters ship in `characters/`. `kyle-brennan` is a deliberate negative example: run `score` on his aliases to watch the generic-branding and overused penalties fire.

## Scoring

Twelve weighted components, each 0–1, combined into a 0–100 score and then reduced by any penalties:

| Component | Weight | Reads |
| --- | --- | --- |
| `authenticity` | 3.0 | Understatement and specificity over cyber-warrior branding. |
| `memorability` | 3.0 | Length, character variety, digit load. |
| `character_resonance` | 3.0 | Tag overlap with the profile. |
| `scene_fit` | 2.0 | Culture, profession, subcultural signal. |
| `legibility` | 2.0 | Is the source word still readable through the mutation? |
| `aesthetic_fit` | 2.0 | Archetype against the requested register. |
| `interface_usability` | 2.0 | Typing, ambiguous glyphs, separator load. |
| `uniqueness` | 2.0 | Distance from the rest of the cast. |
| `contradiction_value` | 2.0 | Does the handle conceal rather than announce? |
| `era_fit` | 1.5 | Period plausibility of archetype and vocabulary. |
| `speakability` | 1.5 | Survives being read aloud in dialogue. |
| `oldschool_signal` | 1.0 | Period styling, rewarded only when asked for. |

Penalties are multiplicative and reported separately: generic branding (−30%), each `overused` element (−9%, capped), and anything on the character's `avoid` list (−45%).

Override any weight per system file:

```json
"score_weights": { "speakability": 3.0, "oldschool_signal": 0.0 }
```

The **authenticity** score intentionally penalizes obvious constructions such as `CyberWarrior` or `EliteHacker`. A technically sophisticated character does not necessarily need a technically obvious handle.

The **contradiction value** is particularly useful for fiction. An experienced operator called `mildew` can be more interesting than `DarkCyberPhantom`, because the former tells the reader almost nothing while potentially becoming meaningful through reputation.

## Scoring handles you wrote

`score` accepts one handle per line, with an optional archetype after a TAB:

```text
null	minimal
mildew	ironic
opcode	technical
janitor	mundane
```

```bash
python nameforge.py score \
  --profile characters/mara-vale.json \
  --system profiles/underground-hacker-handle.json \
  --names candidates.txt --cast characters --verbose
```

Handles that violate the system's own rules are still scored, flagged, and reduced by 40% rather than silently dropped.

## Output formats

`--format table|json|csv|md`, and `--output <path>` writes the same results to a file (the extension picks the format). Markdown groups results by archetype with each archetype's note — useful to paste straight into story notes.

```bash
python nameforge.py generate --profile characters/mara-vale.json \
  --system profiles/underground-hacker-handle.json \
  --top 20 --per-archetype 3 --format md --output shortlist.md
```

## Reproducibility

`--seed` makes a run reproducible. Ties break on the handle text, so the same seed and inputs always produce the same ordering. `--stats` prints pool diagnostics — how many candidates were attempted, why they were rejected, and how wide the score spread is.

## Cast collision detection

Put character JSON files in `characters/`, each with an `aliases` array, then:

```bash
python nameforge.py cast-check characters/ --threshold 0.68
```

It reports high and moderate similarity between aliases, and flags initial-letter crowding — four characters whose handles all start with `n` is the collision readers actually notice.

## Important limitation

This is a heuristic creative tool. It does not determine whether a handle was historically used by a particular person, whether a term belongs to a particular subculture, or whether a reference is culturally appropriate.

For historical fiction, verify specific handles and slang against primary or period sources. The `since`/`until` values in the shipped lexicon are informed estimates for fiction, not citations.

The shipped `scifi` pool deliberately contains no character or place names from published novels or films. Naming a character after someone else's protagonist is an avoidable originality problem, and 2.0's vocabulary was full of them.
