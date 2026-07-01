# AI Dropshipping Automation (backend)

Automates the repetitive backend of a dropshipping store:

1. **Source** trending products from a supplier, filtered by rating/order-volume quality bar.
2. **Write listing copy** (title, description, tags) with Claude, or a template fallback.
3. **Price** each product with a landed-cost markup and push it to the storefront, with inventory.
4. **Fulfill orders**: watch the storefront for new orders, place the matching order with the
   supplier, and mark the storefront order fulfilled once a tracking number comes back.

It runs as a loop (`--loop`) on a schedule, or one cycle at a time (`--once`).

## What this does *not* do

This is backend automation only. It does not create business/bank/ad accounts, does not spend
money on marketing, and does not take on any legal or financial risk on your behalf. You still
need to:

- Register the business entity (if required in your jurisdiction) and set up payment processing.
- Create the actual Shopify store and CJ Dropshipping account, and issue API credentials.
- Review supplier terms, shipping times, and return/refund policy before going live.
- Decide your own pricing/markup and product compliance (no restricted or trademarked items).

## Sandbox mode (default)

With no credentials configured, everything runs against in-memory mock clients
(`suppliers/mock_supplier.py`, `storefront/mock_storefront.py`) that simulate a supplier catalog
and a storefront. This proves out the whole pipeline — sourcing, pricing, listing, and order
fulfillment — before you connect any real account or spend any money.

```bash
cd dropship_automation
pip install -r requirements.txt
cp .env.example .env          # optional in sandbox mode

python -m main --once                    # one full cycle, prints listings + orders
python -m main --simulate-order CJ-1001  # inject a fake customer order, then fulfill it
```

Run from the repo root as `python -m dropship_automation.main --once` if you're not `cd`'d into
the package directory.

## Going live

Fill in `.env` (copy from `.env.example`):

- `SHOPIFY_STORE_DOMAIN` + `SHOPIFY_ACCESS_TOKEN` -> real listings/orders go through
  `storefront/shopify_client.py` (Shopify Admin REST API) instead of the mock.
- `CJ_API_EMAIL` + `CJ_API_KEY` -> real sourcing/ordering goes through
  `suppliers/cj_dropshipping.py` instead of the mock.
- `ANTHROPIC_API_KEY` -> listing copy is written by Claude instead of the template generator.

Both live clients are thin, best-effort wrappers around each provider's public API. API surfaces
change over time — re-check endpoint paths/payloads against current Shopify and CJ Dropshipping
docs before trusting this with real inventory or money. Start by running `--once` against a
Shopify **development store** and a small CJ order before ever running `--loop` against
production.

```bash
python -m main --loop
```

`--loop` runs sourcing/listing on `SOURCING_INTERVAL_HOURS` and order fulfillment on
`FULFILLMENT_INTERVAL_MINUTES` (see `.env.example`), continuously.

## Extending to another platform/supplier

Both integrations are behind small interfaces (`suppliers/base.py::SupplierClient`,
`storefront/base.py::StorefrontClient`). To swap in WooCommerce, Printful, AliExpress, etc.,
implement the interface and wire it into `main.py::build_supplier` / `build_storefront`.

## Tests

```bash
pip install -r requirements.txt
pytest
```

Tests run entirely against the mock clients, no network or credentials required.
