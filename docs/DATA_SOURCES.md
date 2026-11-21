# Data sources and validation

## Selected architecture

- Quotex-labelled venue data: OTCharts read-only API adapter. OTCharts explicitly says it is a third-party provider, not affiliated with Quotex. It requires its own API key. Its free trial is limited to one book, five instruments and 200 requests in the first month; live streaming requires a paid tier. No Quotex password, SSID or browser session is used.
- Independent real-market reference: BiQuote documented REST API adapter for live ticks, symbols and OHLC. Its documentation describes MT5-origin FX/CFD quotes and an OHLC feed built from multiple sources. It is a reference source, not guaranteed to match a particular broker or Quotex payout chart.

## Important market separation

A Quotex OTC instrument such as EURUSD_otc is a separate price series from real EURUSD. Never merge their candles or train one as if it were the other. Compare them only as a divergence/relationship study, and label every chart with venue and market kind.

OTCharts says its Quotex book contains 62 instruments. BiQuote advertises roughly 1,700 catalogue instruments, with only a subset actively quoting at any given moment. "All assets" therefore means all instruments returned by the providers' current catalogues, not every instrument worldwide.

## Configuration

Set OTCHARTS_API_KEY as a secret environment variable to enable OTCharts read-only candle retrieval. Do not commit keys. BiQuote's documented read endpoints currently do not require a key. Confirm provider terms, service status, symbol coverage and data licence before production deployment.

## Parity test protocol

1. Resolve provider symbol IDs from each live catalogue; never guess or reuse IDs across venues.
2. Match only the same underlying instrument and market kind. Keep OTC separate.
3. Normalize timestamps to UTC and align candles by timeframe open time.
4. Compare bid/ask/mid conventions explicitly. A midpoint is not interchangeable with a broker's bid or ask.
5. For each aligned candle, record absolute and relative differences for open/high/low/close, missing bars, timestamp skew, stale events and spread.
6. Report sample size, median, p95 and max error, plus percentage within a tolerance chosen per instrument's tick size.
7. Do not call the feeds matching until a meaningful sample has been collected across market sessions. No signal should be enabled from a stale, incomplete or mismatched feed.

## Safety

This service is data research only. No order execution, account login automation, reverse-engineered private endpoints or credential/session scraping are implemented.
