# Novel Timeline

A small terminal-styled web app for planning the timeline of a novel: place
characters and events on abstract "days," see who is active on any given day,
and spot which characters share the stage.

Everything is stored in one SQLite file, and any project can be exported to /
imported from portable JSON.

## Run it

```bash
pip install -r requirements.txt
python app.py
```

Open <http://127.0.0.1:5000>. A starter project is created automatically the
first time.

The database file is `novel_timeline.db` in the working directory. To use a
different file (e.g. one per book, or a backup):

```bash
NOVEL_DB=my_book.db python app.py
```

## What's in it

**Sidebar** — add and edit *characters* (name, colour, notes, appear/exit day),
*plot threads* (colour-coded), and *locations* (tags for events). Click a
character or thread to filter the timeline to it; click again to release.

**Timeline** (the dashboard) — a swimlane per character. The faded bar is each
character's on-stage span (an open, faded end means "no exit set yet"). Dots are
events, coloured by their plot thread. Drag the day slider or click anywhere on
the grid to move the amber playhead. Zoom in/out with the zoom slider. Click any
dot to edit that event.

**Day / Now** — pick a day and see exactly who is acting that day, grouped by
event (so you can tell who's together vs. off doing their own thing), plus a cast
roster marking each character as *acting*, *on stage*, or *off*.

**Co-occurrence** — a matrix counting, for every pair of characters, how many
days they are both active at the same time. Brighter cells = more shared days.

**Events** — a flat, filterable table of every event.

## Customising

- **Time unit** — rename "Day" to "Chapter," "Cycle," "Session," anything, in
  *settings*. It's used as the label everywhere.
- **Colours** — every character, thread, and location has its own colour picker.
- **Multiple novels** — create as many projects as you like in one database and
  switch between them in the top bar.

## Data / portability

- Working store: SQLite (`novel_timeline.db`).
- **Export** writes a human-readable, diff-friendly JSON file you can back up or
  move between machines. **Import** creates a fresh project from such a file,
  remapping all internal references so nothing breaks.

## Files

```
app.py               Flask backend + SQLite + JSON import/export
templates/index.html Page shell
static/style.css     TUI theme
static/app.js        All views and editors (vanilla JS, no build step)
```
