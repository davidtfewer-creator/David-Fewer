// ============================================================================
// Hybrid10 Feed  —  Power Query replica of the Google Apps Script
// Pulls daily OHLC for ten tickers from the Massive aggregates API and builds
// the Date | <TK>_O/_H/_L/_C table, keeping only dates common to all ten.
//
// Reads inputs FROM THE WORKBOOK (no secrets in this code) via defined names:
//   * FeedConfig  -> range Config!A1:B3   columns  Setting | Value  (ApiKey, StartDate)
//   * FeedTickers -> range Tickers!A1:A11 column   Ticker           (ten rows, in order)
// Paste into: Data > Get Data > Launch Power Query Editor > New Query >
//             Blank Query > Advanced Editor  (replace all).  Name it Hybrid10Feed.
// ============================================================================
let
    // Config / Tickers are workbook DEFINED NAMES (ranges), so promote the first row to headers.
    Cfg     = Table.PromoteHeaders(Excel.CurrentWorkbook(){[Name="FeedConfig"]}[Content], [PromoteAllScalars=true]),
    KEY     = Text.From(Cfg{[Setting="ApiKey"]}[Value]),
    START   = Text.From(Cfg{[Setting="StartDate"]}[Value]),
    TO      = DateTime.ToText(DateTimeZone.RemoveZone(DateTimeZone.UtcNow()), "yyyy-MM-dd"),
    TkTable = Table.PromoteHeaders(Excel.CurrentWorkbook(){[Name="FeedTickers"]}[Content], [PromoteAllScalars=true]),
    Tickers = Table.Column(TkTable, "Ticker"),

    // one ticker -> table [ Date, TK_O, TK_H, TK_L, TK_C ]
    GetTicker = (tk as text) as table =>
        let
            resp = Web.Contents(
                     "https://api.massive.com",
                     [ RelativePath = "v2/aggs/ticker/" & tk & "/range/1/day/" & START & "/" & TO,
                       Query        = [ apiKey = KEY, adjusted = "true", sort = "asc", #"limit" = "50000" ] ]),
            js   = Json.Document(resp),
            res  = js[results],
            tbl  = Table.FromRecords(res),
            keep = Table.SelectColumns(tbl, {"t","o","h","l","c"}),
            dt   = Table.AddColumn(keep, "Date",
                     each Date.From(#datetime(1970,1,1,0,0,0) + #duration(0,0,0,[t]/1000)), type date),
            ren  = Table.RenameColumns(dt, {{"o",tk&"_O"},{"h",tk&"_H"},{"l",tk&"_L"},{"c",tk&"_C"}}),
            sel  = Table.SelectColumns(ren, {"Date", tk&"_O", tk&"_H", tk&"_L", tk&"_C"})
        in
            sel,

    // inner-join every ticker on Date -> keeps only dates present for ALL ten
    first   = GetTicker(Tickers{0}),
    joined  = List.Accumulate(
                List.Skip(Tickers, 1), first,
                (acc, tk) => Table.Join(acc, "Date", GetTicker(tk), "Date", JoinKind.Inner)),

    // column order: Date, then each ticker's O/H/L/C in ticker order
    order   = List.Combine({ {"Date"},
                List.Combine(List.Transform(Tickers, each {_&"_O", _&"_H", _&"_L", _&"_C"})) }),
    sorted  = Table.Sort(Table.ReorderColumns(joined, order), {{"Date", Order.Ascending}}),

    // emit Date as text dd/MM/yyyy to match the Apps Script output exactly
    asText  = Table.TransformColumns(sorted, {{"Date", each Date.ToText(_, "dd/MM/yyyy"), type text}})
in
    asText
