// Website copy deck: summary page + four detail pages with diagrams.
const fs = require('fs');
const {
  Document, Packer, Paragraph, TextRun, HeadingLevel, ImageRun, AlignmentType,
  BorderStyle, LevelFormat, convertInchesToTwip,
} = require('docx');

const NAVY = '182644', TEAL = '176E78', GOLD = 'B08D3B', GREY = '5F5F5F';
const DIR = '/home/user/David-Fewer/website/';

const IMG = {
  d1: { f: 'd1_fair_value.png', w: 1474, h: 859 },
  d2: { f: 'd2_two_models.png', w: 1444, h: 859 },
  d3a: { f: 'd3a_plateau.png', w: 1490, h: 773 },
  d3b: { f: 'd3b_allocation.png', w: 1825, h: 486 },
  d4: { f: 'd4_rails.png', w: 1513, h: 828 },
};

const P = (text, opts = {}) => new Paragraph({
  children: [new TextRun({ text, size: 22, color: '333333', ...opts.run })],
  spacing: { after: 160 }, ...opts.para,
});
const H1 = (text) => new Paragraph({
  heading: HeadingLevel.HEADING_1,
  children: [new TextRun({ text, bold: true, size: 34, color: NAVY })],
  spacing: { before: 320, after: 200 },
});
const H2 = (text) => new Paragraph({
  heading: HeadingLevel.HEADING_2,
  children: [new TextRun({ text, bold: true, size: 25, color: TEAL })],
  spacing: { before: 260, after: 140 },
});
const NOTE = (text) => new Paragraph({
  children: [new TextRun({ text, italics: true, size: 19, color: GREY })],
  spacing: { after: 220 },
});
const LINK = (text) => new Paragraph({
  children: [new TextRun({ text, bold: true, size: 22, color: GOLD })],
  spacing: { after: 300 },
});
const RULE = () => new Paragraph({
  border: { bottom: { style: BorderStyle.SINGLE, size: 8, color: NAVY } },
  spacing: { after: 260 },
});
const IMGP = (key) => {
  const { f, w, h } = IMG[key];
  const width = 620;
  return new Paragraph({
    alignment: AlignmentType.CENTER,
    children: [new ImageRun({
      type: 'png', data: fs.readFileSync(DIR + f),
      transformation: { width, height: Math.round(width * h / w) },
    })],
    spacing: { before: 120, after: 80 },
  });
};
const CAP = (text) => new Paragraph({
  alignment: AlignmentType.CENTER,
  children: [new TextRun({ text, italics: true, size: 18, color: GREY })],
  spacing: { after: 260 },
});
const PAGEBREAK = () => new Paragraph({ children: [], pageBreakBefore: true });

const tile = (num, title, body, link) => [
  new Paragraph({
    children: [
      new TextRun({ text: num + '  ', bold: true, size: 28, color: GOLD }),
      new TextRun({ text: title, bold: true, size: 28, color: NAVY }),
    ],
    spacing: { before: 260, after: 120 },
  }),
  P(body),
  LINK(link + '  →'),
];

const doc = new Document({
  styles: { default: { document: { run: { font: 'Georgia' } } } },
  numbering: {
    config: [{
      reference: 'bullets',
      levels: [{
        level: 0, format: LevelFormat.BULLET, text: '–',
        style: { paragraph: { indent: { left: convertInchesToTwip(0.3), hanging: convertInchesToTwip(0.18) } } },
      }],
    }],
  },
  sections: [{
    properties: {},
    children: [
      // ------------------------------------------------ deck header
      new Paragraph({
        children: [new TextRun({ text: 'Bayesian Capital — website copy', bold: true, size: 40, color: NAVY })],
        spacing: { after: 60 },
      }),
      P('Summary (front) page and four detail pages, with diagrams. The diagram files '
        + '(PNG, brand palette, synthetic data only) accompany this document; each is '
        + 'placed where it belongs with a caption. Link labels are suggestions — wire '
        + 'them to the matching detail page.', { run: { color: GREY, italics: true, size: 20 } }),
      RULE(),

      // ------------------------------------------------ summary page
      H1('PAGE 1 — The front page (summaries)'),
      P('How we trade', { run: { bold: true, size: 30, color: NAVY } }),
      P('A systematic, long-only approach to listed shares: estimate what a stock is '
        + 'worth, bid below it with a margin of safety, and sell at a price fixed in '
        + 'advance. Four ideas carry all of it.'),

      ...tile('01', 'Estimating fair value',
        'A stock’s true value can’t be observed — each day’s price is only a noisy '
        + 'clue. Our models keep a running Bayesian estimate of that value together '
        + 'with a measure of confidence in it, and only buy at a discount to it. When '
        + 'confidence falls, the discount demanded widens automatically.',
        'How we estimate fair value'),

      ...tile('02', 'Two models, two ways of reading the market',
        'A single style of model is fragile. We pair a trend-following value estimate '
        + 'with a mean-reversion model that reads the market the opposite way, so the '
        + 'two bid at different levels and get filled at different moments. Each is '
        + 'kept because it earns its own way — not on a promise to hedge the other.',
        'Why we run two models'),

      ...tile('03', 'Robust settings, careful allocation',
        'Settings that look perfect on past data reliably fail on data they haven’t '
        + 'seen — we have tested this directly, many times. So we choose settings that '
        + 'hold up across a wide range of conditions, leave them alone, and spend our '
        + 'research effort where it actually moves returns: how capital is spread.',
        'Why we don’t chase the perfect backtest'),

      ...tile('04', 'Listed shares, nothing else',
        'Ordinary shares in publicly listed companies — no derivatives, no leverage, '
        + 'no short selling. Every position has its exit price fixed before it is '
        + 'opened and a hard limit on how long it may be held, and no name may take '
        + 'more than an equal share of capital.',
        'The rules every position follows'),

      // ------------------------------------------------ detail page 1
      PAGEBREAK(),
      H1('DETAIL PAGE 1 — How we estimate fair value'),
      NOTE('Suggested URL: /approach/fair-value'),
      P('Most market prices are somebody’s opinion under pressure: a fund rebalancing, '
        + 'a headline, an option desk hedging. Underneath that noise there is something '
        + 'slower-moving — what the business is actually worth to a patient holder. Our '
        + 'starting premise is that this value can never be observed directly. Each '
        + 'day’s closing price is one more noisy measurement of it, nothing more.'),
      H2('A running estimate, with a confidence attached'),
      P('We treat the problem the way an engineer treats a weak radio signal: filter '
        + 'it. A Bayesian filter maintains two numbers for every stock, every day — '
        + 'the current best estimate of underlying value, and how much confidence that '
        + 'estimate deserves. When a new price arrives, the filter weighs it against '
        + 'what it already believes: a price close to expectations nudges the estimate '
        + 'a little; a wild one is largely discounted as noise. Confidence itself moves '
        + 'with the market — the wider a stock’s daily trading range, the less any '
        + 'single price is trusted, automatically and without anyone touching a dial.'),
      H2('Confidence sets the price we are willing to pay'),
      P('The estimate and the confidence work as a pair. Our bid each morning is the '
        + 'estimated value minus a safety margin, and the margin is measured in units '
        + 'of the model’s own uncertainty: calm market, tight band, small discount '
        + 'demanded; turbulent market, wide band, and the model steps its bid down '
        + 'until the price on offer compensates for how little it knows. How deep that '
        + 'discount runs is a deliberately conservative choice — tested against decades '
        + 'of market behaviour, then held fixed rather than tuned to the latest data.'),
      IMGP('d1'),
      CAP('The three layers: noisy daily prices, the model’s running estimate of value '
        + 'with its confidence band, and the resulting bid. In the rough patch the band '
        + 'widens and the bid steps further away.'),
      P('The result is a discipline no discretionary process quite matches: the model '
        + 'is most demanding exactly when markets are most disorderly, and it never '
        + 'pays up for a stock merely because the price is rising.'),

      // ------------------------------------------------ detail page 2
      PAGEBREAK(),
      H1('DETAIL PAGE 2 — Why we run two models'),
      NOTE('Suggested URL: /approach/two-models'),
      P('Every model is a lens, and every lens has a blind spot. A trend-following '
        + 'estimate of value shines when a stock is moving with conviction — and '
        + 'struggles when the market chops sideways. Lean on one lens alone and its '
        + 'bad weeks are your bad weeks, everywhere at once.'),
      H2('The same stock, read two ways'),
      P('So each stock we trade is run by two independent models with opposite '
        + 'instincts. The first is the Bayesian value estimate described on the '
        + 'previous page: it moves with the market and buys measured dips inside an '
        + 'intact move. The second is a mean-reversion model: it anchors on a long-run '
        + 'average and treats a deep stretch below that anchor as the opportunity — '
        + 'fading the move the first model is following.'),
      IMGP('d2'),
      CAP('One market, two bids. The trend model’s bid rides close under the price and '
        + 'catches shallow dips early; the mean-reversion model’s bid sits far below '
        + 'and fills on a different day, at a different price.'),
      H2('Different levels, different moments'),
      P('Because the two read the market in opposite ways, they bid at different '
        + 'levels and get filled at different moments — a shallow intraday dip reaches '
        + 'one, only a genuine dislocation reaches the other. Each finds trades the '
        + 'other misses, and each runs its own capital, compounding on its own results.'),
      H2('Held to an honest standard'),
      P('We are deliberate about why both stay in the book: each earns its keep '
        + 'independently, on its own measured record. We do not keep the second model '
        + 'on a story that it will cushion the first — we measure how the two actually '
        + 'behave together, continuously, and let the evidence rather than the '
        + 'assumption decide.'),

      // ------------------------------------------------ detail page 3
      PAGEBREAK(),
      H1('DETAIL PAGE 3 — Why we don’t chase the perfect backtest'),
      NOTE('Suggested URL: /approach/robustness'),
      P('Give a computer a few years of prices and enough dials, and it will find '
        + 'settings that look extraordinary — on those years. We know, because we have '
        + 'run the experiment on ourselves, repeatedly: re-fit our own models to '
        + 'recent data and the backtest reliably improves, then reliably fails on data '
        + 'it has never seen. Across dozens of controlled trials, the freshly-tuned '
        + 'version has beaten the untouched one only a handful of times.'),
      IMGP('d3a'),
      CAP('The overfitting picture. The sharp spike is the backtest’s favourite '
        + 'setting; on new data it vanishes. The broad hill is slightly less '
        + 'impressive on paper and still there when conditions shift. We choose the hill.'),
      H2('Settings built to be slightly wrong'),
      P('Our response is to stop competing for the peak. We choose settings that sit '
        + 'on broad plateaus — where being somewhat wrong costs little — stress them '
        + 'against deliberately perturbed versions of themselves, and then leave them '
        + 'alone. We have also tested the premise underneath re-tuning itself: whether '
        + 'the market’s statistical character actually drifts on timescales a re-fit '
        + 'could track. It does not. What varies is volatility, and the models absorb '
        + 'that day by day on their own.'),
      H2('The lever that actually matters'),
      P('What moves realised returns far more than any dial is allocation: which '
        + 'stocks are in the book, and how capital is divided across them and between '
        + 'the two models. That is where our research is concentrated — admission of a '
        + 'new name is a formal, evidence-heavy decision, not a hunch. Capital is '
        + 'spread equally, and every sleeve compounds independently: winners are not '
        + 'skimmed to top up losers.'),
      IMGP('d3b'),
      CAP('The book’s structure: equal capital per name, split equally between the two '
        + 'models. Each cell compounds on its own.'),
      H2('Checked before it trades'),
      P('Every model is independently rebuilt and reconciled figure-by-figure before '
        + 'it is trusted, and every result we act on is tested on data withheld from '
        + 'its design. Nothing trades real capital on an in-sample number.'),

      // ------------------------------------------------ detail page 4
      PAGEBREAK(),
      H1('DETAIL PAGE 4 — The rules every position follows'),
      NOTE('Suggested URL: /approach/rules'),
      P('We trade ordinary shares in publicly listed companies — and only shares. No '
        + 'options, futures, CFDs or other derivatives, no borrowed money, no short '
        + 'selling. A position is only ever stock, fully paid for. That single choice '
        + 'removes entire categories of risk: nothing can be called away, margin can '
        + 'never force a sale, and the worst case is bounded before the trade exists.'),
      H2('The lifecycle is decided in advance'),
      P('Every position is born with its ending already written. The entry is a limit '
        + 'order resting below the market — we buy on a dip at our price or not at '
        + 'all, never chasing. The exit price is fixed before the position is opened. '
        + 'And a hard time limit caps how long any position may be held: if the target '
        + 'has not been reached by then, the position is closed anyway, without '
        + 'debate. No exception has ever been made.'),
      IMGP('d4'),
      CAP('One position’s life: bought on a dip at a pre-placed limit, sold at an exit '
        + 'price fixed at entry — with a hard time limit waiting behind it.'),
      H2('One framework, tuned per stock'),
      P('The same framework runs across a deliberately varied range of stocks, tuned '
        + 'to each one — no two names trade alike, and the models’ settings reflect '
        + 'that. Diversification is enforced structurally: no single name may take '
        + 'more than an equal share of capital, so no position, however loved, can '
        + 'dominate the book.'),
      P('None of these rules improves a backtest. They exist so that when we are '
        + 'wrong — and a systematic trader is wrong often — the cost is a bounded, '
        + 'survivable number, decided on a calm day rather than a volatile one.'),
    ],
  }],
});

Packer.toBuffer(doc).then((buf) => {
  fs.writeFileSync(DIR + 'website_copy.docx', buf);
  console.log('written website_copy.docx', buf.length, 'bytes');
});
