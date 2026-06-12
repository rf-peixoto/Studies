# Bitcoin Explorer module

A clickable Bitcoin blockchain explorer for the OSINT Console platform,
refactored from the *bitcrawler* CLI. It queries a Blockstream/Esplora-compatible
API to look up addresses and transactions and lets you walk the transaction
graph by clicking links instead of typing commands.

## Install

Drop this `bitcoin/` folder into the platform's `modules/` directory and restart.
No binary or extra service is required — it talks to an HTTP API. The module then
appears on the dashboard and under **Admin → Modules**.

## What it does

- **Search** an address or a 64-character transaction ID (auto-detected).
- **Address view:** balance (BTC + sats), total received/sent, transaction count,
  and a list of recent transactions — each links to its transaction view.
- **Transaction view:** confirmation status, time, block, fee, size, and the full
  input/output breakdown:
  - Each **input** links back to the funding transaction and to the spending
    address.
  - Each **output** links to the receiving address and, if already spent, forward
    to the spending transaction. Unspent outputs are marked **UTXO**.

That hyperlink navigation replaces the old CLI's `iN`/`oN` commands and the
manual *chain dump/load* — the browser's history is the trail you walked, so
there's nothing to save or reload.

## Settings (admin)

| Setting          | Default                          | Notes                                  |
| ---------------- | -------------------------------- | -------------------------------------- |
| API base URL     | `https://blockstream.info/api`   | Esplora-compatible                     |
| Network label    | `mainnet`                        | Shown in the UI                        |
| Recent txs       | 10                               | How many to list on an address         |
| Request timeout  | 10 s                             | Per API call                           |

Point the base URL at `https://blockstream.info/testnet/api` for testnet, or at
your own [Esplora](https://github.com/Blockstream/esplora) node (e.g.
`http://your-node:3002`) to keep lookups off a third party.

## Persistence

None beyond the settings above, which use the platform's JSON config store
(`get_module_config` / `save_module_config`). The explorer holds no per-user
state and creates no database.

## Security notes

- Addresses and transaction IDs are validated (txid = 64 hex; address =
  length-bounded alphanumeric, a safe superset of base58/bech32) and passed
  through the platform-wide character blacklist (`assert_clean`) before being
  URL-encoded into the API path.
- Outbound requests use the platform's shared User-Agent and timeout. Lookup
  routes are rate-limited (90/hour/IP) since each hits an external API.
- All admin forms carry CSRF tokens; the explorer requires an authenticated
  session, and configuration requires an admin.

## Responsible use

The default API is a public third-party service that sees every address and
transaction you query. For sensitive investigations, run lookups against your own
Esplora node. Only investigate what you are authorised to.
