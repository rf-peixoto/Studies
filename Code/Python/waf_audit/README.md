# WAF audit (updated)

Install: `pip install -r requirements.txt` (optionally `pip install wafw00f` for `--active`).

Basic: `python waf_audit.py targets.txt -o results.csv`

IP enrichment: `python waf_audit.py targets.txt --ip-check -o results.csv`

**Focus on potential unprotected targets:**
`python waf_audit.py targets.txt --focus-unprotected -o results.csv`

With optional WAFW00F probes (only where authorized):
`python waf_audit.py targets.txt --focus-unprotected --active -o results.csv`

Outputs: results.csv (all entries), results_candidates.csv (no recognizable WAF/CDN signatures after available checks), results_candidates.txt (URLs), results_inconclusive.csv (cannot reliably classify). The candidate label **does not prove the absence of a WAF/CDN**. Cloudflare and Fastly CIDR inventories are checked; this is not an exhaustive provider database. Failure to retrieve ranges makes negative classifications inconclusive. Requests are sent to public HTTP(S) URLs; the IP check does not probe IPs directly. A CDN does not imply an enabled WAF. The script intentionally preserves HTTP/HTTPS host-based behavior.
