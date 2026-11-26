param(
    [Parameter(Mandatory = $true)][string]$LogisimExe,
    [string]$JavaExe = 'java',
    [string]$JavacExe = 'javac',
    [string]$CompilerJar
)
$ErrorActionPreference = 'Stop'
$LogisimExe = (Resolve-Path -LiteralPath $LogisimExe).Path
$buildDir = Join-Path $PSScriptRoot '.build'
$sourceFile = Join-Path $PSScriptRoot 'NativeSystemCheck.java'
$circuitFile = Join-Path $PSScriptRoot '../SnakeSystem.circ'
New-Item -ItemType Directory -Path $buildDir -Force | Out-Null
if ($CompilerJar) {
    & $JavaExe -jar $CompilerJar -1.8 -encoding UTF-8 -nowarn -cp $LogisimExe -d $buildDir $sourceFile
} else {
    & $JavacExe -encoding UTF-8 -cp $LogisimExe -d $buildDir $sourceFile
}
if ($LASTEXITCODE -ne 0) { throw 'Java test compilation failed.' }
& $JavaExe '-Djava.awt.headless=true' -cp "$buildDir;$LogisimExe" NativeSystemCheck $circuitFile
if ($LASTEXITCODE -ne 0) { throw 'Native simulation checks failed.' }
