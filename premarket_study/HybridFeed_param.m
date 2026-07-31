// ============================================================================
// Hybrid10 Feed  —  Power Query replica (parameter version, firewall-safe)
// Uses ONLY the web API as a data source: tickers + start date are literals here,
// and the API key comes from a Power Query PARAMETER named  ApiKey  (not the sheet).
// Because nothing is read from the workbook, the Formula Firewall / "gateway" error
// cannot occur.
//
// SETUP:
//   1. Power Query Editor > Home > Manage Parameters > New Parameter
//        Name = ApiKey , Type = Text , Current Value = <paste your Massive key>
//   2. New Query > Blank Query > Advanced Editor > paste this > Done.
//   3. Rename the query Hybrid10Feed > Close & Load To... > Table > =Data!$A$1.
//   4. First refresh: set api.massive.com credentials to Anonymous.
// ============================================================================
let
    KEY     = ApiKey,                              // <- Power Query parameter
    START   = "2024-04-01",                        // feed start date (edit here if needed)
    Tickers = {"NVDA","TSM","TSLA","VRT","VST","AVGO","PLTR","RKLB","SOFI","SPOT"},
    TO      = DateTime.ToText(DateTimeZone.RemoveZone(DateTimeZone.UtcNow()), "yyyy-MM-dd"),

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

    first   = GetTicker(Tickers{0}),
    joined  = List.Accumulate(
                List.Skip(Tickers, 1), first,
                (acc, tk) => Table.Join(acc, "Date", GetTicker(tk), "Date", JoinKind.Inner)),
    order   = List.Combine({ {"Date"},
                List.Combine(List.Transform(Tickers, each {_&"_O", _&"_H", _&"_L", _&"_C"})) }),
    sorted  = Table.Sort(Table.ReorderColumns(joined, order), {{"Date", Order.Ascending}}),
    asText  = Table.TransformColumns(sorted, {{"Date", each Date.ToText(_, "dd/MM/yyyy"), type text}})
in
    asText
