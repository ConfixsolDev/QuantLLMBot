# Evidence Brief — Cross-Timeframe Influence and Session Bias in XAUUSD

Prepared for the `complete_market_structure` fine-tuning curriculum, v002.
This brief records what the published literature actually supports, so the 50 new
stage-01 principles can be honest about which of their own claims are tested.

Nothing here is copied from any book, paper or website. All principle text in
`train.jsonl` is original restatement, consistent with the dataset's existing
`source_policy`.

---

## The hypothesis under test

Two claims were put forward:

1. **Timeframe cascade.** Candle movement starts on M1, but it is always the higher
timeframe that influences the lower — D1 and H4 shape H1, which shapes M30/M15,
which shapes M5/M1. The relationship between those pairs is readable.

2. **Session bias with a juke.** The Asian session's directional outcome biases the
London session the same way — if Asia opens at one price and closes higher, London
tends to continue — but London first shows a counter-move ("juke") that takes out a
prior extreme before resolving into the real direction.

Both were researched for supporting *and* refuting evidence. The verdicts differ
sharply, and that difference is the single most useful result of this exercise.

---

## Claim 1: the timeframe cascade — SUPPORTED, but only for volatility

This is the strongest finding in the whole survey, and it is also the one most likely
to be misapplied.

There is a real, peer-reviewed, replicated body of work showing that **coarser-timeframe
volatility predicts finer-timeframe volatility better than the reverse.** This is the
Heterogeneous Market Hypothesis, developed on high-frequency FX data by Müller,
Dacorogna, Davé, Olsen and Pictet (*Journal of Empirical Finance*, 1997) and formalised
in the HARCH model. Corsi's HAR-RV model (*Journal of Financial Econometrics*, 2009)
built a forecasting model directly on this cascade — daily, weekly and monthly realized
volatility components predicting next-period volatility — and reported out-of-sample
R² around 0.61 on USD/CHF and 0.70 on the S&P 500. Zumbach and Lynch (*Physica A*, 2001)
tested the causal direction explicitly rather than assuming it, and confirmed the
long-to-short asymmetry. The same machinery has since been applied to gold futures
realized volatility with good results.

So the mechanism the hypothesis describes is real. **What it is not is directional.**
Every paper in this line forecasts the *magnitude* of movement. None forecasts sign.
A recent gold-specific HAR study says this explicitly: improved volatility forecasts
identify high-uncertainty regimes that inform position sizing and risk management, but
do not generate directional alpha.

Two further caveats matter:

The asymmetry is not universal. Chicheportiche and Bouchaud, decomposing volatility
feedback into overnight and intraday components, found the fine-to-coarse link at least
as strong as the coarse-to-fine link on that particular split. "Higher always drives
lower" is a tendency across many observations, not a law that holds in every window.

And multi-timeframe analysis *as a trading technique* — using an HTF trend filter to
improve LTF entries — has essentially no peer-reviewed literature at all. The void is
itself a finding. The only backtests available are broker and blog content without
out-of-sample validation. Meanwhile Sullivan, Timmermann and White (*Journal of Finance*,
1999) tested roughly 7,800 technical rules across a century of index data and found none
survived correction for data-snooping bias.

**Net:** keep the timeframe hierarchy, but route it into range expectation, stop
geometry and position sizing — not into direction. Principles 011, 022, 023, 025 and
054 encode exactly that split.

---

## Claim 2: Asian → London directional bias — UNTESTED, with evidence pulling both ways

No peer-reviewed study was found that regresses London-session return on the prior
Asian-session return. This specific question is simply open.

What *is* established is the session seasonality underneath it. Andersen and Bollerslev
(1997) documented strong intraday periodicity in FX volatility. Ito and Hashimoto (2006),
using EBS interbank tick data, mapped activity peaks at the Tokyo open, the London open
and the London/NY overlap, with lunch-hour troughs — and found that the size of the
Tokyo-to-London price change correlates with inter-regional trading volume. BIS survey
data confirms London carries roughly 38% of global spot turnover and that activity peaks
in the London/NY overlap. All of that is about **activity and volatility**, not direction.

On direction, the closest tested analogues split:

Supporting continuation, Gao, Han, Li and Zhou (*Journal of Financial Economics*, 2018)
found the first half-hour return predicts the last half-hour return in SPY, statistically
significant but with in-sample R² of about 1.6% — real, and small. Elaut, Frömmel and
Lampaert (*Journal of Financial Markets*, 2018) found a similar intraday momentum effect
in RUB/USD, and attributed it to liquidity-provider inventory risk rather than informed
trading.

Cutting the other way, published work on weekend overreaction in spot FX found that large
directional gaps across a session boundary tend to **reverse**, across eight major and
nine emerging pairs, with the reversal surviving transaction costs.

The bare "Asian range breakout" rule fares poorly where it has been tested at all — the
public backtests found report roughly 54% directional accuracy with per-trade P&L near
zero before costs. The academically respectable cousin, opening range breakout, was tested
by Holmberg, Lönnbark and Lundström (*Finance Research Letters*, 2013) on 28 years of WTI
crude and did show win rates of 54–71% surviving modest costs — but the authors state
plainly that results are not robust to time, with profits concentrated in the volatile
2001–2011 window.

**Net:** the Asian→London bias is a hypothesis worth measuring, not a rule worth trading.
Principle 031 records it as exactly that; 032 and 033 hold the supporting and refuting
evidence side by side rather than discarding the inconvenient one.

---

## The juke — folklore with a real mechanism underneath

The "Judas swing" / London-open false move has **no rigorous test in either direction**.
Every source located is a definitional page, an indicator listing, an educational
walkthrough carrying a "simulated results do not represent actual trading" disclaimer, or
a cherry-picked YouTube chart. No sample size, no win rate with a confidence interval, no
out-of-sample test. This should be stated plainly: not weak evidence — *no* evidence.

But there is a genuinely well-supported mechanism that would produce behaviour that looks
exactly like it. Osler (*Journal of Finance*, 2003), using roughly 9,700 real conditional
orders from a major bank, showed that **stop-loss and take-profit orders cluster
differently around salient prices**. Take-profit orders concentrate *at* round numbers
(9.3% executing exactly at "00"), which makes price reverse there. Stop-loss orders
concentrate *just past* round numbers (14.4% in the .01–.10 band above, versus 7.4% in the
.90–.99 band below), which makes price accelerate once the level is exceeded. Her follow-up
(*JIMF*, 2005) modelled the resulting price cascades. Simulated behaviour matched actual
exchange-rate behaviour at similar magnitude.

That is the honest version of "liquidity sweep." Orders really do pile up at visible
prices, and price really does behave differently around those piles. The gap between Osler
and the folklore is that she tested round numbers with real order data, while the
practitioner claim is specifically about the Asian session high/low being systematically
swept — which nobody has isolated and tested. Principles 034, 036, 037 and 038 carry this
distinction, and 058 forbids intent attribution: describe that liquidity was taken, don't
narrate who hunted whom.

One gold-specific note: the pre-2015 London PM gold benchmark did show a statistically
anomalous downside skew in large moves over 2004–2013 (in 2010, on as many as 92% of days).
The authors acknowledged no clear mechanism, benign explanations exist involving PM-window
liquidity and US data timing, and the benchmark was restructured in 2015. Principle 042
records it as elevated event risk, not as a directional rule.

---

## Source texts for further distillation

Fifteen of the seventeen candidate books are under active copyright, so all distillation
must remain conceptual restatement. The two cleanly public-domain works are Wyckoff's
*Studies in Tape Reading* (1910) and Lefèvre's *Reminiscences of a Stock Operator* (1923),
both freely available via the Internet Archive and Project Gutenberg respectively.

Highest value for this curriculum, by theme: Dalton's *Mind Over Markets* and Steidlmayer's
*Markets and Market Logic* for the auction/acceptance-rejection vocabulary that the
`auction_assessment` field already uses; Harris's *Trading and Exchanges* for order-book and
resting-order mechanics, which doubles as a rigour counterweight; Lien's *Day Trading and
Swing Trading the Currency Market* for session structure; Elder's *Trading for a Living* for
the canonical top-down formalization; and Aronson's *Evidence-Based Technical Analysis* as
the primary skeptical counterweight — it should shape the tone of the whole dataset rather
than one theme, which is what principles 048 through 060 attempt.

---

## How this lands in the dataset

Fifty new stage-01 examples, `principle_011` through `principle_060`, in the exact existing
message schema. Each carries three record-level metadata fields the training text does not
see:

- `evidence_strength` — one of `strong` (24), `moderate` (21), `weak` (3), `untested` (2)
- `evidence_basis` — what the support actually is
- `evidence_sources` — author, year, title

The point of that labelling is principle 060: stated confidence should be capped by the
weakest critical link in the evidence chain behind a decision. A visually perfect setup
built entirely on untested doctrine is a low-confidence trade.
