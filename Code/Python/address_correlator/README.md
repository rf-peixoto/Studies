# ADDRESS_CORRELATOR

A local, terminal-styled Flask tool: drop addresses on a dark map, tag and
color them, and draw correlations between markers that share a tag or color.
Built for Brazilian address data, with strong geocoding fallbacks.

## Run

```bash
cd address_correlator
python3 -m venv venv && source venv/bin/activate     # optional
pip install -r requirements.txt
python app.py
```

Open http://127.0.0.1:5000

## Adding markers

Three ways:

1. **Type an address** – street, number, neighborhood, city, state. It's
   geocoded and dropped on the map with your chosen name/tag/color.
2. **Manual coordinates** – expand "MANUAL COORDINATES" in the INPUT panel and
   type `lat` + `lon` by hand. This skips geocoding entirely, so any address
   that won't resolve can still be placed exactly where you want it.
3. **Bulk .txt upload** – one entry per line (see format below).

### Fields
- **name** – individual label shown on the map (toggle with "SHOW MARKER NAMES").
- **tag** – the correlation group key (kept separate from the name, so you can
  have distinct names *and* a shared group).
- **color** – marker color; also usable as a correlation grouping key.

## Bulk upload format

Plain `.txt`, one entry per line:

```
address;tag or color
```

- If the second field is a valid hex color (`#8cff66`, `#abc`) it's used as the
  **marker color**.
- Anything else is treated as a **tag**, and each distinct tag is auto-assigned
  a color from a palette.
- Optional 3-field form keeps an explicit name: `address;name;tag_or_color`
- Lines that are blank, start with `//`, or start with `#` (without a `;`) are
  skipped as comments.

`sample_addresses.txt` is included, generated from your dataset, ready to upload.

> Uploads geocode at ~1 request/second (Nominatim's usage policy), so a large
> file takes a little while. Unresolved lines are reported in the status
> message and can be added afterward with manual coordinates.

## Correlation view

In the CORRELATION panel:

- **GROUP MARKERS BY**: `TAG`, `COLOR`, or `NONE`.
- **LINK STYLE**:
  - `LINES` – connects each group's markers to their shared centroid.
  - `REGION` – draws a convex-hull polygon around each group.
  - `LINES + REGION` – both.

All groups render at the same time, each in its own color, with a legend
listing every group and its marker count. Group overlays sit *below* the
markers so pins and labels stay readable.

## Geocoding notes (Brazilian addresses)

The geocoder tries progressively looser variants until one resolves:

1. the address as typed;
2. with `, Brazil` appended and a Brazil country filter;
3. with street abbreviations expanded (`R`→Rua, `AV`→Avenida, `TV`→Travessa,
   `JD`→Jardim, `VL`→Vila, `PRQ`→Parque, …);
4. with unit/block fragments removed (`AP 2`, `BLOCO 02 APTO 302`, …);
5. dropping the street segment → neighborhood level;
6. dropping again → city level.

Each marker records which precision level resolved it, shown as a small badge in
the DATASET list (`exact` / `street` / `neighborhood` / `city` / `manual`) so
you can see at a glance which pins are approximate.

## Reset

"CLEAR DATASET" removes every marker. To wipe the database file entirely, stop
the app and delete `instance/addresses.db`.
