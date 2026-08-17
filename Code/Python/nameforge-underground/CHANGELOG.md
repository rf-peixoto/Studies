# Changelog

## 2.1.0 — review, bug fixes, lexicon enrichment

### Scoring bugs (these were distorting every ranking)

**Two thirds of the pool was scored with the wrong archetype.**
`transform_pool` relabelled every mutation `"<archetype>+transform"`. That string was then looked up in `archetype_tags`, `ARCHETYPES` and every archetype bonus set, where it always missed. Measured on the shipped 2.0 data: 1407 of 2207 candidates had a character-resonance of exactly 0.0, against a mean of 3.31 for untransformed ones. Mutations now keep their archetype, and their provenance is recorded separately in `Build.transforms`.

**The score was capped at ~87/100 and the generic penalty was counted twice.**
`generic_penalty` was subtracted from `authenticity` *and* added as a component with weight `-3.0`, while `denom = sum(abs(w))` kept that 3.0 in the denominator. A flawless handle could never exceed 86.96. Penalties are now multiplicative, applied once, reported separately, and the full 0–100 range is reachable.

**Resonance was normalised by the wrong set.**
`overlap(a, b)` returned `len(A & B) / len(B)` where `B` was the character's expanded desired-impression set (26 tags in the shipped profile) and `A` was the archetype's two tags. Maximum achievable resonance was therefore 2/26. Matching now runs the profile side through alias expansion and the handle side through canonicalisation, and saturates at three matches.

**Only 36 distinct scores across 2207 candidates** — 1214 of them shared a single value, because the score depended almost entirely on the archetype label and a length cliff. After the rewrite: 1074 distinct scores across 1560 candidates. Length now uses a smooth falloff instead of `len(h) in preferred_lengths`, and four handle-level components were added (`legibility`, `speakability`, `era_fit`, plus digit and glyph analysis).

**`overused` was dead configuration.** The field was loaded, documented, and never read by any code path. It is now a real penalty.

**Substring matching was too crude for it**, once wired in: a naive test flags `neon` for containing `neo`. `contains_element` now requires a whole word, a prefix/suffix of 4+ characters, or an embedded substring of 5+.

**Entropy was normalised against a hardcoded 4.0 bits**, so short handles always looked low-entropy regardless of shape. It now normalises against `log2(len)`, the actual ceiling.

**A character was compared against itself** when its own file was in the `--cast` directory, guaranteeing a 100% self-collision warning.

### Generation bugs

**`orthographic` returned unmodified dictionary words 53% of the time** and **`leet` returned leet-free words 26% of the time**, because both included the unchanged source in their variant set. Measured over 500 samples each on the 2.0 data. Both now use `strict=True` variants and return `None` rather than emitting a clean word under a mutation label.

**`minimal` was not minimal.** It truncated to `rng.choice(preferred_lengths)`, which ranged up to 12 — usually longer than the source word, so it returned the word intact. It now truncates to 3–6 characters.

**`compound` produced doubled halves** — `echoecho`, `voidvoid` — because the left and right pools overlapped and nothing checked. `compound_is_degenerate` now rejects identical halves, containment, and heavy shared prefixes.

**Corruption produced typos, not style.** The doubled-letter and dropped-second-character rules generated `heexdump` and `cooredump`, which read as mistakes. Both removed. A `legibility` component now penalises mutations that bury the source word.

**The separator transform cut words at random offsets**, producing `uma-sc64`. It now only splits at a real boundary between two source terms.

**Mutations stacked without limit**, so corrupt + phonetic + leet could compound into noise. Spelling mutations are now capped at one per handle.

**`--pool 800` produced 2207 candidates**, because transforms expanded the pool after the count was satisfied. Variants per base handle are now capped (`max_variants=3`) and `--stats` reports the real numbers.

**`--archetype` accepted only what argparse listed**, and that list was maintained separately from the scoring tables, the README and the `init` template — four copies that had already drifted. All archetype metadata now lives in one `ARCHETYPES` dict.

**Silent failure on impossible requests.** `generate_handle_pool` looped `count * 30` times and returned however many handles it managed, with no indication. It now reports rejection reasons via `--stats` and warns when it falls short.

### CLI and robustness bugs

**`--no-color` did nothing.** `main()` computed a `color` flag and never passed it anywhere; `paint()` defaulted to `enabled=True`. ANSI codes were emitted into pipes and files. Colour is now a module-level switch, `--color` forces it on, and the banner is suppressed when stdout is not a terminal.

**Every coloured column was misaligned**, because `f"{paint(x):22}"` padded a string containing 9 invisible escape characters. `pad()` measures visible width.

**A missing profile raised `TypeError: Character.__init__() missing 1 required positional argument: 'id'`** instead of the `FileNotFoundError` that `main()` was already catching, because `load_json` returned `{}` for a missing path. Missing files now raise properly, malformed JSON reports line and column, and unknown fields warn instead of being silently dropped.

**`cmd_system` shadowed the imported `field` from `dataclasses`** with its loop variable.

**Unused import** (`itertools.product`), **`math` imported inline** via `__import__("math")` inside a hot function, **`lower` listed as a transformation** despite being a no-op after normalisation (`normalize_handle` already lowercases), and **`json.JSONDecodeError` caught alongside `ValueError`** when it is already a subclass.

**`init` wrote the same profile to two filenames** (`underground-handle.json` and `underground-character.json`), then printed only the second. The README documented the second; the shipped archive contained only the first. `init` now copies the real template files, and the canonical name is `underground-character.json`.

### Data problems in the shipped JSON

- Duplicate entries inside single pools (`socket`, `static`, `janitor` each appeared twice), biasing random selection toward them.
- 14 terms duplicated across pools (`signal`, `void`, `zero`, `ghost`, `node`, `proxy`, `relay`, `wire`, `static`, `echo`, `daemon`, `cipher`, `entropy`, `sprawl`), so a "compound" of two different pools could return the same word twice.
- `cyber` appeared in `prefixes` while also being on `overused` and in the generic-branding penalty list: the system generated handles it then penalised.
- `ghost` and `shadow` were both in the vocabulary pools and on the `overused` list, same contradiction.
- The `scifi` pool consisted largely of character and place names lifted from published novels and films. Using those verbatim as a character's alias is an avoidable originality problem for a novelist. Replaced with genre vocabulary that carries the same texture without borrowing anyone's protagonist.

### New

- **Enriched lexicon.** 270 terms across 11 pools (was 155 across 7), every one carrying tags, a gloss, a period range, a pick weight and a register. Two new registers of vocabulary that the tool's own design philosophy calls for but 2.0 lacked: `organic` (the "mildew" family) and `bureaucratic`.
- **New pools:** `crypto`, `organic`, `bureaucratic`, `phreak`.
- **New archetypes:** `acronym`, `phonetic`, and `seeded` — the last builds from the writer's own `seed_words` (surnames, places, private jokes), which is the one input a generic lexicon can never supply.
- **`doctor` command.** Validates a system file: duplicates, cross-pool collisions, terms that can never pass validation, vocabulary that collides with your own `overused` list, and archetypes your vocabulary cannot build. `--strict` exits non-zero.
- **Period plausibility.** `since`/`until` per term, era ranges per archetype, and an `era_fit` component that warns when a 2011 character reaches for `bluebox` or leetspeak.
- **Explanations.** Every candidate now prints the gloss of the words it was built from, which tags it matched, which transforms were applied, and which penalties fired.
- **`--format json|csv|md`** and `--output`; markdown groups by archetype for pasting into story notes.
- **`--per-archetype`** caps how many results one archetype may occupy, with an automatic hint when the shortlist is lopsided.
- **`--year`, `--seed-word`, `--avoid`, `--min-score`, `--no-transform`, `--stats`.**
- **New character fields:** `first_online_year`, `languages`, `interests`, `handle_history`, `avoid`, `seed_words`.
- **`analyze --system`** identifies which lexicon terms a handle contains and whether it passes the system's rules.
- **`cast-check`** now also reports initial-letter crowding, and reads `handle_history` alongside `aliases`.
- **Five example characters**, including one deliberate negative example.
- **Test suite: 5 tests → 43**, with a `TestRegressions` class pinning each bug above.
- **`score_weights`** in the system file, for tuning the ranking per project.
