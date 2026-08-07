"""
Prepend a branded title page to research PDFs whose LaTeX sources we do not have.

Why this way. Changing a document's body font means re-typesetting it, which without the .tex
source means re-keying tables, maths and figures out of a PDF -- a reliable way to put silent
transcription errors into a research record. Adding a title page does not: the original pages
are embedded verbatim by pdfpages, so every figure in the document is byte-for-byte what the
author produced. Nothing here touches content.

What it produces. An A4 (or matched-size) title page carrying the house monogram, the document's
own title and subtitle lifted from its first page, the Bayesian Capital block and the
confidentiality line -- then the original document, unaltered, from page 2 on.

Known limitation, stated rather than discovered later: prepending shifts every printed page
number by one, and pdfpages does not carry through the source document's internal hyperlinks or
bookmarks. For documents that already open with their own title block the result is two title
pages, one branded and one not. Both are the price of not re-typesetting; if a document matters
enough to want it clean, supply the .tex and it can be rebuilt properly.

Run:  python3 brand_titlepages.py
"""
import os
import re
import subprocess

UP = '/root/.claude/uploads/822d405e-f99b-5b59-9c6b-87e725054402'
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'branded')
LOGO = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'assets', 'bc_logo.pdf')

# Titles and subtitles read off each document's own first page. Dates are included only where
# the document states one; nothing is invented.
DOCS = [
    ('7f888704-Automating_the_Hybrid_Model_with_IBKR__step_plan',
     'From Spreadsheet to Robot',
     'A Step-by-Step Plan to Automate the Hybrid Trading Model with Interactive Brokers',
     '24 June 2026'),
    ('56818e39-Book__company_summaries_16_stocks',
     'The Book --- Company Summaries',
     'The 16 stocks traded by the Bayesian + OU model, grouped by theme',
     ''),
    ('6b316b81-Drift_vs_volatility__return_analysis',
     "How Much of the Model's Return Is the Bull Market?",
     'A drift-versus-volatility decomposition of the five-stock Bayesian + OU model',
     '24 June 2026'),
    ('731ab8a4-Fivestock_screen_and_optimisation',
     'Screening and Optimising a Second Cohort',
     'Finding five more stocks for the Bayesian + OU model --- search, screen, fit',
     ''),
    ('70dc9539-Fourstock_model_optimisation',
     'Extending the Bayesian + OU Model to Four New Stocks',
     'Stock characteristics and how each was used to optimise the parameters',
     ''),
    ('4831e875-NVDA_premium_analysis',
     'Premium Sensitivity of the NVIDIA Model',
     'Why total profit rises, falls and rises again as the sell premium is increased',
     ''),
    ('5914b8ff-NVDA_trading__handoff_brief',
     'NVDA Systematic Trading --- Project Handoff Brief',
     'A self-contained context document for continuing the work',
     '10 June 2026'),
    ('54e9b915-NVDA_trading_strategy_survey',
     'NVDA Systematic Trading --- A Survey of Strategies',
     'From mean-reversion and Bayesian entries to the Ornstein--Uhlenbeck hedge',
     '10 June 2026'),
    ('92ec6f58-NVDA_vs_TSM__optimisation_differences',
     'Why NVIDIA and TSMC Optimise Differently',
     'Entry depth and the source of edge in a Bayesian dip-buying model',
     '12 June 2026'),
    ('752cd5cc-Sameday_sequencing_and_candidate_reassessment',
     'Same-Day Sequencing',
     'Re-assessment of the book and the diversifier candidates',
     ''),
    ('335dc806-Summary',
     'Summary',
     'NVDA systematic trading: strategies and tranching',
     '10 June 2026'),
    ('65127994-Trading_strategy__mathematics',
     'A Tranched Mean-Reversion, Premium-Capture Trading Strategy',
     'Mathematical reference --- basics, with an expanded Bayesian section',
     '3 June 2026'),
    ('afebe29a-Walkforward_testing__method_and_elimination_criteria',
     'Walk-Forward Testing',
     'How it works, and how to know an elimination is sound',
     ''),
    ('333b436a-daily_trading_system_guide',
     'The Daily Trading System',
     'A plain-English guide to how the automation works',
     ''),
]

TEMPLATE = r"""\documentclass[11pt]{article}
\usepackage[papersize={%(pw).2fpt,%(ph).2fpt},margin=1in]{geometry}
\usepackage[T1]{fontenc}
\usepackage{xcolor}
\usepackage{graphicx}
\usepackage{pdfpages}
\definecolor{bcnavy}{RGB}{14,30,60}
\definecolor{bcgold}{RGB}{176,135,60}
\definecolor{bcgrey}{RGB}{90,90,90}
\pagestyle{empty}
\begin{document}
\begin{center}
\vspace*{%(top)s}
\includegraphics[width=%(logo).1fcm]{%(logo_path)s}

\vspace{34pt}
{\color{bcgrey}\rule{0.42\textwidth}{0.5pt}}

\vspace{20pt}
{\color{bcnavy}\fontsize{%(tsize)d}{%(tlead)d}\selectfont\bfseries %(title)s}

\vspace{12pt}
{\color{bcnavy}\fontsize{12}{16}\selectfont %(subtitle)s}

\vspace{20pt}
{\color{bcgold}\rule{0.42\textwidth}{1.0pt}}

\vspace{44pt}
{\color{bcnavy}\normalsize\bfseries Bayesian Capital}\\[4pt]
{\color{bcgrey}\normalsize Systematic Trading Research}%(dateline)s

\vspace{20pt}
{\color{bcgrey}\small\itshape Internal document --- strictly confidential}
\end{center}
\clearpage
\includepdf[pages=-,fitpaper=true]{%(src)s}
\end{document}
"""


def page_size(path):
    info = subprocess.run(['pdfinfo', path], capture_output=True, text=True).stdout
    m = re.search(r'^Page size:\s+([\d.]+) x ([\d.]+)', info, re.M)
    return (float(m.group(1)), float(m.group(2))) if m else (595.28, 841.89)


def main():
    os.makedirs(OUT, exist_ok=True)
    ok, bad = [], []
    for stem, title, subtitle, date in DOCS:
        src = os.path.join(UP, stem + '.pdf')
        if not os.path.exists(src):
            bad.append((stem, 'source missing'))
            continue
        pw, ph = page_size(src)
        name = re.sub(r'^[0-9a-f]{8}-', '', stem)
        # long titles need a smaller face to stay on two lines
        tsize, tlead = (21, 27) if len(title) < 46 else (17, 22)
        dateline = ('\\\\[4pt]\n{\\color{bcgrey}\\normalsize %s}' % date) if date else ''
        tex = TEMPLATE % dict(pw=pw, ph=ph, top='0.9in', logo=4.8, logo_path=LOGO,
                              tsize=tsize, tlead=tlead, title=title, subtitle=subtitle,
                              dateline=dateline, src=src)
        wrap = os.path.join(OUT, name + '.tex')
        with open(wrap, 'w') as f:
            f.write(tex)
        for _ in range(2):
            subprocess.run(['pdflatex', '-interaction=nonstopmode', '-halt-on-error',
                            os.path.basename(wrap)], cwd=OUT, capture_output=True)
        pdf = os.path.join(OUT, name + '.pdf')
        if os.path.exists(pdf):
            before = subprocess.run(['pdfinfo', src], capture_output=True, text=True).stdout
            after = subprocess.run(['pdfinfo', pdf], capture_output=True, text=True).stdout
            b = int(re.search(r'^Pages:\s+(\d+)', before, re.M).group(1))
            a = int(re.search(r'^Pages:\s+(\d+)', after, re.M).group(1))
            (ok if a == b + 1 else bad).append((name, f'{b} -> {a} pages'))
        else:
            bad.append((name, 'compile failed'))
    for n, s in ok:
        print(f'  OK    {n:56s} {s}')
    for n, s in bad:
        print(f'  FAIL  {n:56s} {s}')
    print(f'\n{len(ok)} branded, {len(bad)} failed. Output in {OUT}')
    for f in os.listdir(OUT):
        if f.rsplit('.', 1)[-1] in ('aux', 'log', 'out', 'tex'):
            os.remove(os.path.join(OUT, f))


if __name__ == '__main__':
    main()
