# Bitcoin Explorer & Investigation module

A Bitcoin investigation tool for the OSINT Console platform, refactored and grown
from the *bitcrawler* CLI. It runs on a Blockstream/Esplora-compatible HTTP API
and has two layers:

* **Explorer** — look up an address or transaction and click through the graph
  (inputs, outputs, spends). Every txid, address and spent output is a link.
* **Investigation** — a persistent, monitored workspace that watches the chain
  for you and traces coins over time.

## Install

Drop this `bitcoin/` folder into the platform's `modules/` directory and restart.
No binary or extra service is required — it talks to an HTTP API. It appears on
the dashboard and under **Admin → Modules**.

## The three investigation capabilities

### 1. Watch an address → "new activity" tag
Open any address and click **Watch this address**. The first scan records a
silent baseline; after that, whenever coins move **in or out**, the address gets
a **new activity** tag on the dashboard and the transaction is added to its
recorded-activity feed, labelled *received* / *sent* / *self*. The tag clears
when you open the address.

### 2. Watch a transaction → "confirmed" tag
Open a transaction and click **Watch this transaction**. While unconfirmed it
shows as such; the moment it confirms it gets a **newly confirmed** tag and a
live confirmation count (chain tip − block height + 1). The tag clears when you
open the transaction.

### 3. Flag a coin → trace it backward and forward (the core)
A "coin" is a single transaction output, an **outpoint** written `txid:vout`.
Flag one from the **⚑ Flag** button on any output in a transaction view, or paste
an outpoint on the dashboard. Flagging immediately:

* **Maps provenance (the past).** Walks the input ancestry of the funding
  transaction up to *provenance depth*, so you can see where the coins came from
  (terminating at coinbase / freshly mined coins).
* **Starts forward tracing (the future).** Watches the flagged outpoint; the
  moment it is spent, it follows the spending transaction's outputs as the next
  hops — automatically, hop after hop — so you learn **when and where** the coins
  move. Freshly discovered hops carry a **new** tag and the coin is marked
  *moved*. Unspent endpoints are listed as the coins' current resting places.

The coin detail page shows all three: current location(s), the forward trail, and
the provenance, each hop linking back into the explorer.

#### Honesty about tracing
Bitcoin transactions merge many inputs and split into many outputs, so once coins
pass through a transaction the downstream outputs are not provably the *same*
coins. This tool follows **all** outputs of each spending transaction (standard
taint analysis) and annotates every hop with a proportional **taint %** =
(our input value ÷ that transaction's total input value), so you can judge
dilution. Depth and node caps keep a trace bounded; if a trace is capped you'll
see a notice and can raise the limits in settings.

## Monitoring

A background poller refreshes every watched address, transaction and flagged coin
on an interval (default 300 s, configurable, minimum 60 s) and can be turned off.
You can also hit **Check all now**, or **Re-trace now** on a single coin, to
refresh on demand. The workspace is **shared** across authenticated operators
(a shared case file); each row records who created it.

> Multi-worker note: the auto-poller runs one loop per process. Under a
> multi-worker WSGI server, either run a single worker for the poller, disable
> auto-poll and drive **Check all now** from a scheduled job, or front it with one
> dedicated instance.

## Settings (admin)

| Setting              | Default                        | Notes                                   |
| -------------------- | ------------------------------ | --------------------------------------- |
| API base URL         | `https://blockstream.info/api` | Any Esplora-compatible endpoint         |
| Network label        | `mainnet`                      | Shown in the UI                         |
| Recent txs           | 10                             | Listed on an address                    |
| Request timeout      | 10 s                           | Per API call                            |
| Politeness delay     | 0.4 s                          | Pause between API calls while tracing   |
| Auto-poll            | on                             | Background monitoring                    |
| Poll interval        | 300 s                          | Minimum 60 s                            |
| Provenance depth     | 3                              | How far back a coin is mapped           |
| Max forward depth    | 6                              | How far forward spends are followed     |
| Max hops / coin      | 60                             | Safety cap on a trace's size            |

Point the base URL at `https://blockstream.info/testnet/api` for testnet, or at
your own [Esplora](https://github.com/Blockstream/esplora) node
(`http://your-node:3002`) to keep lookups private.

## Persistence

Tunable settings use the platform's JSON config store. The monitored workspace
(watched addresses, watched transactions, flagged coins and their trace graphs)
lives in a **module-private SQLite database** — `bitcoin.db` inside this folder,
overridable with `BITCOIN_DB_PATH`. As with the subdomains module, this keeps
append-heavy, background-written relational data out of the core database (which
modules never touch) and is removed when the module is deleted.

## Security notes

* Addresses and txids are validated (txid = 64 hex; address = length-bounded
  alphanumeric) and passed through the platform character blacklist
  (`assert_clean`) before being URL-encoded into the API path.
* Outbound requests use the platform's shared User-Agent and timeout. Lookup and
  flag routes are rate-limited; all forms carry CSRF tokens; the explorer
  requires an authenticated session and configuration requires an admin.

## Responsible use

The default API is a public third-party service that sees every address and
transaction you query. For sensitive investigations, run against your own Esplora
node. Trace results are investigative leads, not proof of ownership — read the
taint caveat above. Only investigate what you are authorised to.
