# 25-slot managed book — design spec (23 Oct 2026)

Agreed with the user across HANDOVER §3.88–3.99. This is the brief for the workbook build.

## Slots and tiers

| Tier | Slots | Names | Behaviour |
|---|---|---|---|
| Core | 12 | TSM VRT VST AVGO MU GM VLO CF MRVL RTX DE NVDA | Trades every day as today |
| Bench | 5 | NEM LEN DLTR RKT TEAM | Funded only by cash the breadth gate holds back |
| Shadow | 8 | PLTR TSLA RKLB APLD AAOI CEG UAL LUNR | Model runs, orders computed and logged, nothing sent |
| Off | any | — | Name's morning share is HELD IN CASH (never redistributed) |

Every slot has the same fixed rows and columns, so tier changes never move the layout Script 1 and
Script 2 depend on.

## Rules (Script 1, every morning)

1. Breadth count = core names whose prior close is below their own 200-day average.
2. Count ≥ 6: each core name below its own average places no buy; its share is held back.
3. Held-back cash is lent to Bench orders, each at most one ordinary sleeve share.
4. Exposure cap: no name's held value (prior close) + today's orders may exceed 25% of equity.
   Applies to every name, and to the user's discretionary tickets.
5. Off: the name's share is held in cash.
6. Orders never exceed cash (cash account).
7. Unchanged: PM rule (09:00, 4%), ATH gate (ε = 0), 50-day stop, frozen vectors.

## Parameter panel — review cadence

| Parameter | Value | Tested | Review |
|---|---|---|---|
| Tier per slot (Core/Bench/Shadow/Off) + reason | as above | §3.98 | Daily (decision, logged) |
| Discretionary tickets (inside the cap, 10-session stop enforced) | — | §3.77 | Daily |
| Emergency stop: place no new buys | off | — | Daily |
| Exposure cap per name | 25% | 10–30%, §3.97 | Weekly look, change quarterly |
| Liquidity cap per name (order vs typical first-hour volume) | TO TEST | §3.99 | Weekly look |
| Capital | $6.9m → ~$10m | §3.99 | Monthly |
| Shadow admission / removal decisions | — | §3.99 | Monthly |
| Breadth K | 6 of 12 | 3–6, §3.94 | Quarterly, only with a two-regime backtest |
| Gate average length | 200 days | 50/100, §3.96 | Quarterly, as above |
| PM rule cut / threshold | 09:00 / 4% | §3.16 | Quarterly |
| ATH gate ε | 0 | §3.86 | Quarterly |
| Time stop | 50 calendar days | 10–60, §3.81–3.82 | Annual |
| Model vectors | frozen | refits fail OOS, §3.1 | Annual, walk-forward evidence only |

## Daily monitoring panel

- Book value, peak, drawdown from peak; cash and idle %
- Breadth count and distance to 6; each core name's % above/below its 200-day average
- Gate status; bench lending today ($ and to whom)
- Each name's share of equity vs the 25% cap (model + discretionary)
- Positions within 10 sessions of the 50-day stop; discretionary tickets past their stop
- Pre-market flags; ATH-gate blocks
- Orders placed vs filled today, against the model's expected fill rate
- Shadow orders and paper P&L
- Data health: last update per feed
- Liquidity flag: today's order vs the name's typical first-hour at-bid volume

## Shadow panel (monitored daily)

One row per Shadow name: why it is not in the book, what admission requires, and the live
evidence accumulating against each requirement (see HANDOVER §3.99 for the reasons table).

## Admission tests (monthly review, quarterly re-run)

1. Role — diversifier (AI beta < 0.27) for the bench; AI-related names only as a core replacement.
2. Settings carry over — fittability rho ≥ 0.20 for a fitted vector, else neutral with a positive
   random-vector median.
3. Book test in both regimes — adding it must not lower the latest test-half return by > 1pp or
   raise the 2022 (or any stress) max drawdown; re-run each quarter as data extends.
4. Liquidity at current capital — p95 first-hour participation ≤ 5–10%, stops ≤ a set share of the
   opening 30 minutes. Needs a volume column.
5. Shadow conduct — ≥ 3 months and ≥ 10 shadow orders: live fill rate and premium capture within
   tolerance of the model, no data gaps. This checks execution and data, not edge.
6. Risk decisions remain the user's.

Removal: a core or bench name failing test 3 on two consecutive quarterly re-runs, failing test 4
at current capital, or a fundamental event (user decision, logged).
