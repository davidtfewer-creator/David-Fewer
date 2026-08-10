"""
Conceptual diagrams for the website detail pages. Synthetic data only — nothing
proprietary. Brand palette: navy ink #182644, teal #176E78 (trend model), gold
#B08D3B (mean-reversion model), grey #5F5F5F, grid #E7E7E2.
"""
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

NAVY, TEAL, GOLD, GRey, GRID = '#182644', '#176E78', '#B08D3B', '#5F5F5F', '#E7E7E2'
OUT = '/home/user/David-Fewer/website/'
rng = np.random.default_rng(7)


def frame(ax):
    ax.spines[['top', 'right']].set_visible(False)
    ax.spines[['left', 'bottom']].set_color(GRID)
    ax.tick_params(colors=GRey, labelsize=9)
    ax.grid(True, color=GRID, lw=0.6, alpha=0.7)
    ax.set_axisbelow(True)


def savefig(fig, name):
    fig.savefig(OUT + name, dpi=200, bbox_inches='tight', facecolor='white')
    plt.close(fig)
    print('wrote', name)


# ---------------------------------------------------------------- D1 fair value
n = 130
t = np.arange(n)
vol = np.where((t > 55) & (t < 85), 2.6, 1.0)          # a rough patch mid-series
steps = rng.normal(0.25, 1.0, n) * vol
level = 100 + np.cumsum(steps * 0.55)
price = level + rng.normal(0, 1.1, n) * vol

fair = np.copy(price)
band = np.zeros(n)
b = 2.2
for i in range(1, n):
    g = 0.28
    fair[i] = fair[i - 1] + 0.25 + g * (price[i] - (fair[i - 1] + 0.25))
    band[i] = 0.9 * band[i - 1] + 0.1 * (abs(price[i] - fair[i]) * 2.6 + 1.2)
band[0] = band[1]
bid = fair - b * band

fig, ax = plt.subplots(figsize=(9, 4.6))
frame(ax)
ax.fill_between(t, fair - band, fair + band, color=NAVY, alpha=0.13, lw=0)
ax.plot(t, price, 'o', ms=2.4, color=GRey, alpha=0.65)
ax.plot(t, fair, color=NAVY, lw=2.0)
ax.plot(t, bid, color=GOLD, lw=2.0, ls=(0, (5, 3)))
ax.annotate('each day’s price — a noisy clue', xy=(20, price[20]), xytext=(3, 118),
            color=GRey, fontsize=10, arrowprops=dict(arrowstyle='-', color=GRey, lw=0.8))
ax.annotate('the model’s running estimate of value', xy=(105, fair[105]), xytext=(62, 132),
            color=NAVY, fontsize=10, fontweight='bold',
            arrowprops=dict(arrowstyle='-', color=NAVY, lw=0.8))
ax.annotate('the bid: value minus a safety margin', xy=(100, bid[100]), xytext=(58, 84),
            color=GOLD, fontsize=10, fontweight='bold',
            arrowprops=dict(arrowstyle='-', color=GOLD, lw=0.8))
ax.annotate('calm: a small discount\nis enough', xy=(38, bid[38]), xytext=(14, 88),
            color=GRey, fontsize=9,
            arrowprops=dict(arrowstyle='->', color=GRey, lw=0.8))
ax.annotate('rough patch: confidence falls,\nthe demanded discount widens', xy=(70, bid[70]),
            xytext=(70, 74), color=GRey, fontsize=9,
            arrowprops=dict(arrowstyle='->', color=GRey, lw=0.8))
ax.set_xlabel('time (trading days)', color=GRey, fontsize=9)
ax.set_yticklabels([])
savefig(fig, 'd1_fair_value.png')

# ---------------------------------------------------------------- D2 two models
n = 150
t = np.arange(n)
base = 100 + 0.35 * t + 9 * np.sin(t / 16.0)
price = base + np.cumsum(rng.normal(0, 0.75, n))
ema = np.copy(price)
for i in range(1, n):
    ema[i] = ema[i - 1] + 0.30 * (price[i] - ema[i - 1])
long_run = np.copy(price)
for i in range(1, n):
    long_run[i] = long_run[i - 1] + 0.045 * (price[i] - long_run[i - 1])
bid_tr = ema - 4.5
bid_mr = long_run - 9.0

fill_tr = [i for i in range(20, n) if price[i] <= bid_tr[i - 1]]
fill_mr = [i for i in range(20, n) if price[i] <= bid_mr[i - 1]]

fig, ax = plt.subplots(figsize=(9, 4.6))
frame(ax)
ax.plot(t, price, color=GRey, lw=1.1, alpha=0.75)
ax.plot(t, bid_tr, color=TEAL, lw=2.0)
ax.plot(t, bid_mr, color=GOLD, lw=2.0, ls=(0, (5, 3)))
if fill_tr:
    i = fill_tr[0]
    ax.plot(i, price[i], 'o', ms=9, mfc=TEAL, mec='white', mew=1.5, zorder=5)
    ax.annotate('the trend model buys a shallow dip\nwhile the move is intact',
                xy=(i, price[i]), xytext=(i - 46, price[i] + 22), color=TEAL,
                fontsize=9.5, fontweight='bold',
                arrowprops=dict(arrowstyle='->', color=TEAL, lw=1.0))
if fill_mr:
    i = fill_mr[0]
    ax.plot(i, price[i], 's', ms=9, mfc=GOLD, mec='white', mew=1.5, zorder=5)
    ax.annotate('the mean-reversion model waits for a\ndeep stretch below the long-run average',
                xy=(i, price[i]), xytext=(i + 6, price[i] - 24), color=GOLD,
                fontsize=9.5, fontweight='bold',
                arrowprops=dict(arrowstyle='->', color=GOLD, lw=1.0))
ax.text(n - 1, bid_tr[-1] + 1.5, 'trend model’s bid', color=TEAL, fontsize=10,
        fontweight='bold', ha='right', va='bottom')
ax.text(n - 1, bid_mr[-1] - 2.0, 'mean-reversion model’s bid', color=GOLD, fontsize=10,
        fontweight='bold', ha='right', va='top')
ax.text(30, price[30] + 13, 'market price', color=GRey, fontsize=10)
ax.set_xlabel('time (trading days)', color=GRey, fontsize=9)
ax.set_yticklabels([])
savefig(fig, 'd2_two_models.png')

# ---------------------------------------------------------------- D3a plateau
x = np.linspace(0, 1, 600)
hill = 0.62 * np.exp(-((x - 0.68) / 0.16) ** 2)
spike = 0.95 * np.exp(-((x - 0.27) / 0.022) ** 2)
insample = hill + spike + 0.05
unseen = 0.92 * hill + 0.10 * spike + 0.02

fig, ax = plt.subplots(figsize=(9, 4.4))
frame(ax)
ax.plot(x, insample, color=GRey, lw=1.6, ls=(0, (4, 3)))
ax.plot(x, unseen, color=NAVY, lw=2.2)
ax.annotate('the tempting spike: perfect in the\nbacktest, gone on data it hasn’t seen',
            xy=(0.27, 1.0), xytext=(0.03, 0.78), color=GRey, fontsize=9.5,
            arrowprops=dict(arrowstyle='->', color=GRey, lw=0.9))
ax.annotate('', xy=(0.27, 0.16), xytext=(0.27, 0.93),
            arrowprops=dict(arrowstyle='->', color=GOLD, lw=1.6))
ax.annotate('the broad hill: slightly less impressive,\nstill there when conditions shift — we choose here',
            xy=(0.68, 0.62), xytext=(0.45, 0.86), color=NAVY, fontsize=9.5, fontweight='bold',
            arrowprops=dict(arrowstyle='->', color=NAVY, lw=0.9))
ax.text(0.985, insample[-1] + 0.05, 'looks like this in the backtest', color=GRey,
        fontsize=9.5, ha='right')
ax.text(0.985, unseen[-1] - 0.055, 'performs like this on new data', color=NAVY,
        fontsize=9.5, fontweight='bold', ha='right')
ax.set_xlabel('a model setting', color=GRey, fontsize=9)
ax.set_ylabel('return', color=GRey, fontsize=9)
ax.set_yticklabels([]); ax.set_xticklabels([])
savefig(fig, 'd3a_plateau.png')

# ---------------------------------------------------------------- D3b allocation
fig, ax = plt.subplots(figsize=(9, 2.9))
ax.set_xlim(0, 8.6); ax.set_ylim(-0.3, 2.6)
ax.axis('off')
for i in range(8):
    ax.add_patch(plt.Rectangle((i + 0.06, 1.28), 0.88, 0.88, color=TEAL, alpha=0.92))
    ax.add_patch(plt.Rectangle((i + 0.06, 0.24), 0.88, 0.88, color=GOLD, alpha=0.92))
    ax.text(i + 0.5, 2.32, f'name {chr(65+i)}', ha='center', color=GRey, fontsize=9)
ax.text(8.18, 1.72, 'trend model', color=TEAL, fontsize=10.5, fontweight='bold', va='center')
ax.text(8.18, 0.68, 'mean-reversion\nmodel', color=GOLD, fontsize=10.5,
        fontweight='bold', va='center')
ax.text(0.06, -0.18, 'equal capital per name, split equally between the two models — '
        'each cell compounds on its own and is never topped up from the others',
        color=GRey, fontsize=9.5)
savefig(fig, 'd3b_allocation.png')

# ---------------------------------------------------------------- D4 rails
n = 90
t = np.arange(n)
price = 100 + np.cumsum(rng.normal(0.0, 0.9, n))
price[:12] -= np.linspace(0, 4, 12)[::-1]              # early dip to fill the bid
entry_day = 10
entry = price[entry_day]
target = entry * 1.055
limit_day = 70
hit = next((i for i in range(entry_day + 1, n) if price[i] >= target), None)
if hit is None:
    price[40:] += (target - price[40:].max()) + 1.5
    hit = next(i for i in range(entry_day + 1, n) if price[i] >= target)

fig, ax = plt.subplots(figsize=(9, 4.4))
frame(ax)
ax.plot(t[:hit + 1], price[:hit + 1], color=GRey, lw=1.3)
ax.plot(t[hit:], price[hit:], color=GRID, lw=1.1, ls=':')
ax.hlines(target, entry_day, limit_day, color=GOLD, lw=2.0)
ax.axvline(limit_day, color=NAVY, lw=1.4, ls=(0, (4, 3)))
ax.plot(entry_day, entry, 'o', ms=10, mfc=TEAL, mec='white', mew=1.6, zorder=5)
ax.plot(hit, price[hit], '^', ms=11, mfc=GOLD, mec='white', mew=1.6, zorder=5)
ax.annotate('entry: a limit order below the market,\nnever a chase', xy=(entry_day, entry),
            xytext=(15, entry - 7.5), color=TEAL, fontsize=9.5, fontweight='bold',
            arrowprops=dict(arrowstyle='->', color=TEAL, lw=1.0))
ax.annotate('the exit price — set before the\nposition is opened', xy=(34, target),
            xytext=(30, target + 6), color=GOLD, fontsize=9.5, fontweight='bold',
            arrowprops=dict(arrowstyle='->', color=GOLD, lw=1.0))
ax.annotate('sold at the target', xy=(hit, price[hit]), xytext=(hit + 6, price[hit] - 6),
            color=GOLD, fontsize=9.5,
            arrowprops=dict(arrowstyle='->', color=GOLD, lw=0.9))
ax.text(limit_day + 1, price.min() + 1, 'hard time limit:\nif the target has not been\n'
        'reached by here, the position\nis closed anyway', color=NAVY, fontsize=9)
ax.set_xlabel('days held', color=GRey, fontsize=9)
ax.set_yticklabels([])
savefig(fig, 'd4_rails.png')
print('all diagrams done')
