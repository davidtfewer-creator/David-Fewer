# Maths notes and summaries

Summaries of **Text & Tests 4 (New Edition), Chapter 1 — "Algebra 1"** (Leaving Certificate
Higher Level), covering Sections 1.1–1.10.

| File | Length | What it is |
|---|---|---|
| `algebra1_summary_5pp.tex` | exactly 5 pages | Condensed revision sheet: definitions, every formula, the method recipes, one worked example per idea. |
| `algebra1_summary_10pp.tex` | exactly 10 pages | Fuller version: the same structure plus the long-division layout in full, Pascal's triangle, difference tables, a glossary, more worked examples, a revision checklist and a wrong/right table of common mistakes. |
| `algebra1_key_questions.tex` | 1 page + appendix | Thirty-three key questions drawn from Exercises 1.1–1.10 and the Revision Exercises, one page in two columns, each referenced back to the book; the appendix gives full solutions with the working. |

The two summaries cover theory, methods and worked examples only — the book's exercises are
deliberately kept out of them, and live in the separate questions sheet instead. Every answer in
the solutions appendix was checked symbolically with SymPy.

**Conventions.** All mathematics is set in LaTeX. Anything a reader should know by heart is
highlighted in light purple (`\key{...}`, via `soul`); formulae sit in light-purple boxes and
step-by-step methods in boxes with a purple banner. Inside a purple box, where a highlight
would be invisible, `\keyin{...}` sets the same emphasis in deep purple bold instead.

Note: inside `\key{...}`, mathematics has to be written literally as `\mbox{$...$}` — `soul`
cannot handle a macro that takes an argument.

## Building

```
pdflatex algebra1_summary_5pp.tex
pdflatex algebra1_summary_10pp.tex
pdflatex algebra1_key_questions.tex
```

Requires `soul`, `tcolorbox`, `enumitem`, `titlesec`, `xcolor`, `textcomp` (on Debian/Ubuntu:
`texlive-latex-base`, `texlive-latex-recommended`, `texlive-fonts-recommended`,
`texlive-latex-extra`). The PDFs are not committed — `*.pdf` is gitignored at the repo root.

## Source

Scanned chapter supplied as a 47-page PDF. Page 37 of that scan is cropped, so part of
Exercise 1.9 and the opening of Section 1.10 are missing from the source; the summaries
reconstruct Section 1.10 from pages 38–41, which carry all of its theory and examples.

One erratum in the printed book is flagged in the 10-page summary: in the binomial worked
example on page 21, `(1 − 5y)^8` is printed as `(1 − 3y)^8` in the third line; the arithmetic
that follows is that of `(1 − 5y)^8`.
