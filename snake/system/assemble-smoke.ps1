param(
    [Parameter(Mandatory = $true)][string]$RarsJar,
    [string]$JavaExe = 'java'
)
$ErrorActionPreference = 'Stop'
$RarsJar = (Resolve-Path -LiteralPath $RarsJar).Path
$wordsFile = Join-Path ([IO.Path]::GetTempPath()) ('snake-smoke-' + [guid]::NewGuid() + '.words')
try {
    & $JavaExe '-Djava.awt.headless=true' -jar $RarsJar nc a ae1 mc CompactTextAtZero dump .text HexText $wordsFile (Join-Path $PSScriptRoot 'io-smoke.asm')
    if ($LASTEXITCODE -ne 0) { throw 'RARS assembly failed.' }
    $words = [IO.File]::ReadAllLines($wordsFile)
    if ($words.Count -gt 1024 -or $words.Count -eq 0) { throw 'ROM must contain 1 to 1024 words.' }
    foreach ($word in $words) {
        if ($word -notmatch '^[0-9a-fA-F]{8}$') { throw 'Unexpected RARS output.' }
    }
    $hex = "v2.0 raw`n" + ($words -join "`n") + "`n"
    [IO.File]::WriteAllText((Join-Path $PSScriptRoot 'io-smoke.hex'), $hex, [Text.Encoding]::ASCII)
    Write-Output "Wrote io-smoke.hex ($($words.Count) words). Reload it into the main circuit ROM before saving circuit changes."
} finally {
    if (Test-Path -LiteralPath $wordsFile) { Remove-Item -LiteralPath $wordsFile }
}
