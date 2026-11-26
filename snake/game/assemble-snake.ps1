param(
    [Parameter(Mandatory = $true)][string]$RarsJar,
    [string]$JavaExe = 'java'
)
$ErrorActionPreference = 'Stop'
$RarsJar = (Resolve-Path -LiteralPath $RarsJar).Path
$source = Join-Path $PSScriptRoot 'snake.asm'
$hexOut = Join-Path $PSScriptRoot 'snake.hex'
$wordsFile = Join-Path ([IO.Path]::GetTempPath()) ('snake-game-' + [guid]::NewGuid() + '.words')
try {
    & $JavaExe '-Djava.awt.headless=true' -jar $RarsJar nc a ae1 mc CompactTextAtZero dump .text HexText $wordsFile $source
    if ($LASTEXITCODE -ne 0) { throw 'RARS assembly failed.' }
    $words = [IO.File]::ReadAllLines($wordsFile)
    if ($words.Count -gt 1024 -or $words.Count -eq 0) { throw 'ROM must contain 1 to 1024 words.' }
    foreach ($word in $words) {
        if ($word -notmatch '^[0-9a-fA-F]{8}$') { throw 'Unexpected RARS output.' }
    }
    $hex = "v2.0 raw`n" + ($words -join "`n") + "`n"
    [IO.File]::WriteAllText($hexOut, $hex, [Text.Encoding]::ASCII)
    Write-Output "Wrote snake.hex ($($words.Count) words, $($words.Count * 4) bytes)."
} finally {
    if (Test-Path -LiteralPath $wordsFile) { Remove-Item -LiteralPath $wordsFile }
}
