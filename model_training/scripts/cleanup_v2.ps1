# cleanup_v2.ps1 — Remove broken, duplicate and superseded files
#
# Generated 2026-08-08 as part of the v2 canonicalization.
# Every line is commented with why the file is being removed.
# Run from the repo root (E:\QuantLLMBot) or adjust $root below.
#
# REVIEW EACH LINE before running. Nothing is deleted until you execute this.

$root = "E:\QuantLLMBot"
$books = "E:\Trading Books"

# ── Trading Books: broken and duplicate PDFs ─────────────────────────

# Fake Mind over Markets: byte-identical to Brooks Reversals (md5 cffce6a6…)
# The real MoM is now present as Mind_Over_Markets_Power_Trading…pdf
Remove-Item "$books\dalton\Mind over Markets (verify title).pdf" -Verbose

# Brooks Reversals 30-page stub: front matter + index only, no body
# The real 586-page edition is now present
Remove-Item "$books\Al Brooks — Trading Price Action Reversals.pdf" -Verbose

# Alt Trends: 56 MB watermarked scan, 96% duplicate of the clean 17.5 MB copy
Remove-Item "$books\brooks\Al-Brooks-Trading-Price-Action-Trends-alt.pdf" -Verbose

# Nison image scan: 0 extractable text; _text.pdf supersedes
Remove-Item "$books\nison\Japanese Candlestick Charting Techniques 2nd edition 2001.pdf" -Verbose

# Murphy image scan: 0 extractable text; "by John J. Murphy.pdf" supersedes
Remove-Item "$books\murphy\Technical Analysis of the Financial Markets - A Comprehensive Guide to Trading Methods and Applications 1999.pdf" -Verbose

# Grimes duplicate: root annotated copy is content-identical to grimes/ copy
# If your annotations are in the ROOT copy, swap these two lines
Remove-Item "$books\The Art and Science of Technical Analysis - Market Structure, Price Action, and Trading Strategies 2012 - annotated.pdf" -Verbose

# Empty substitutes directory (if it exists)
if (Test-Path "$books\substitutes") { Remove-Item "$books\substitutes" -Recurse -Verbose }

# ── knowledge/_pdf_extract: old truncated and broken extracts ────────
# These are superseded by the full corpus in full_corpus_v2.zip (slug-named files)

$extract = "$root\model_training\knowledge\_pdf_extract"

# Stub from the fake MoM / 30-page Brooks Reversals
Remove-Item "$extract\Mind_over_Markets_(verify_title).txt" -Verbose
Remove-Item "$extract\Al_Brooks_—_Trading_Price_Action_Reversals.txt" -Verbose

# Failed extracts from image-only scans (594 bytes and 1.1KB)
Remove-Item "$extract\Japanese_Candlestick_Charting_Techniques_2nd_edition_2001.txt" -Verbose
Remove-Item "$extract\Technical_Analysis_of_the_Financial_Markets_-_A_Comprehensive_Guide_to_Trading_M.txt" -Verbose

# Duplicate alt-Trends extract
Remove-Item "$extract\Al-Brooks-Trading-Price-Action-Trends-alt.txt" -Verbose

# Old truncated extracts (capped at ~510KB, now replaced by full slug-named versions)
# Only remove these AFTER extracting full_corpus_v2.zip into _pdf_extract/
Remove-Item "$extract\The_Art_and_Science_of_Technical_Analysis_-_Market_Structure,_Price_Action,_and_.txt" -Verbose
Remove-Item "$extract\Day_Trading_and_Swing_Trading_the_Currency_Market_-_Technical_and_Fundamental_St.txt" -Verbose
Remove-Item "$extract\Trading_Price_Action_Trends_-_Technical_Analysis_of_Price_Charts_Bar_by_Bar_for_.txt" -Verbose
Remove-Item "$extract\A_Complete_Guide_to_Technical_Trading_Tactics_-_How_to_Profit_Using_Pivot_Points.txt" -Verbose
Remove-Item "$extract\Come_Into_My_Trading_Room_-_A_Complete_Guide_to_Trading_2002.txt" -Verbose
Remove-Item "$extract\Beyond_Candlesticks_-_New_Japanese_Charting_Techniques_Revealed_1994.txt" -Verbose
Remove-Item "$extract\A_Complete_Guide_To_Volume_Price_Analysis_2013.txt" -Verbose
Remove-Item "$extract\Trading_in_the_Zone_-_Master_the_Market_with_Confidence,_Discipline_and_a_Winnin.txt" -Verbose
Remove-Item "$extract\Trading_Price_Action_Trading_Ranges.txt" -Verbose
Remove-Item "$extract\Markets_in_Profile.txt" -Verbose
Remove-Item "$extract\Trades_About_to_Happen.txt" -Verbose

# Old full extracts with long names (replaced by slug-named versions)
Remove-Item "$extract\Al_Brooks_Trading_Price_Action_Reversals.txt" -Verbose
Remove-Item "$extract\Japanese_Candlestick_Charting_Techniques_2nd_Edition_Steve_Nison_text.txt" -Verbose
Remove-Item "$extract\Technical_Analysis_of_the_Financial_Markets_by_John_J_Murphy.txt" -Verbose
Remove-Item "$extract\Mind_Over_Markets_Power_Trading_with_Market_Generated_Information_Updated_Edition_-_James_.txt" -Verbose
Remove-Item "$extract\Markets_and_Momentum_-_James_F_Dalton.txt" -Verbose

# Old manifest (replaced by corpus_manifest.json in the zip)
Remove-Item "$extract\manifest.json" -Verbose

Write-Host "`nCleanup complete. Estimated reclaim: ~120 MB (PDFs + old extracts)." -ForegroundColor Green
Write-Host "Next: extract full_corpus_v2.zip into $extract\ if not already done." -ForegroundColor Yellow
