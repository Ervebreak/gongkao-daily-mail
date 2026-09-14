param(
    [string]$OutputZip = "",
    [string]$BuildDir = "",
    [string]$PythonVersion = "310",
    [string]$Platform = "manylinux2014_x86_64"
)

$ErrorActionPreference = "Stop"

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$root = Split-Path -Parent $scriptDir
if (-not $OutputZip) {
    $OutputZip = Join-Path $root "function.zip"
}
elseif (-not [System.IO.Path]::IsPathRooted($OutputZip)) {
    $OutputZip = Join-Path $root $OutputZip
}
if (-not $BuildDir) {
    $BuildDir = Join-Path $root "build\fc_linux_py$PythonVersion`_package"
}

function Remove-IfExists {
    param([string]$Path)
    if (Test-Path -LiteralPath $Path) {
        Remove-Item -LiteralPath $Path -Recurse -Force
    }
}

function Assert-Entry {
    param(
        [System.IO.Compression.ZipArchive]$ZipArchive,
        [string[]]$Names
    )
    foreach ($name in $Names) {
        if ($ZipArchive.GetEntry($name) -or $ZipArchive.GetEntry($name.Replace("/", "\"))) {
            return
        }
    }
    throw "Package check failed. Missing required entry: $($Names -join ' or ')"
}

Set-Location $root
New-Item -ItemType Directory -Force -Path (Split-Path -Parent $OutputZip) | Out-Null
Remove-IfExists $BuildDir
New-Item -ItemType Directory -Force -Path $BuildDir | Out-Null

# Copy only runtime source files and runtime assets. Do not copy .git, old zips,
# local outputs, candidates, tests, or dependencies already installed in the repo.
Get-ChildItem -LiteralPath $root -File -Filter "*.py" | Copy-Item -Destination $BuildDir
Copy-Item -LiteralPath (Join-Path $root "requirements.txt") -Destination $BuildDir

foreach ($dir in @("content_harness", "knowledge", "knowledge_base", "scripts", "data")) {
    $src = Join-Path $root $dir
    if (Test-Path -LiteralPath $src) {
        Copy-Item -LiteralPath $src -Destination (Join-Path $BuildDir $dir) -Recurse
    }
}

python -m pip install `
    -r (Join-Path $root "requirements.txt") `
    -t $BuildDir `
    --platform $Platform `
    --python-version $PythonVersion `
    --implementation cp `
    --abi "cp$PythonVersion" `
    --only-binary=:all: `
    --upgrade

python -m py_compile (Get-ChildItem -LiteralPath $BuildDir -File -Filter "*.py" | ForEach-Object { $_.FullName }) `
    (Get-ChildItem -LiteralPath (Join-Path $BuildDir "scripts") -File -Filter "*.py" | ForEach-Object { $_.FullName })

Get-ChildItem -LiteralPath $BuildDir -Recurse -Directory |
    Where-Object { $_.Name -in @("__pycache__", ".pytest_cache") } |
    Remove-Item -Recurse -Force

Get-ChildItem -LiteralPath $BuildDir -Recurse -File |
    Where-Object {
        $_.Name -like "*.pyc" -or
        $_.Name -like "*.log" -or
        $_.Name -like "*.zip" -or
        $_.Name -like "*.pdf" -or
        $_.Name -like "*.xlsx"
    } |
    Remove-Item -Force

Remove-IfExists $OutputZip
Add-Type -AssemblyName System.IO.Compression.FileSystem
[System.IO.Compression.ZipFile]::CreateFromDirectory(
    $BuildDir,
    $OutputZip,
    [System.IO.Compression.CompressionLevel]::Optimal,
    $false
)

$zip = [System.IO.Compression.ZipFile]::OpenRead($OutputZip)
try {
    Assert-Entry $zip @("main.py")
    Assert-Entry $zip @("fc_weekly_render.py")
    Assert-Entry $zip @("fc_candidate_publish.py")
    Assert-Entry $zip @("scripts/build_weekly_package.py", "scripts\build_weekly_package.py")
    Assert-Entry $zip @("requirements.txt")
    Assert-Entry $zip @("question_bank.py")
    Assert-Entry $zip @("scripts/validate_daily_brief.py", "scripts\validate_daily_brief.py")
    Assert-Entry $zip @("data/question_bank/shenlun_question_bank_v3_a.csv", "data\question_bank\shenlun_question_bank_v3_a.csv")
    Assert-Entry $zip @("knowledge_base/policy_corpus/policy_statements_core.jsonl", "knowledge_base\policy_corpus\policy_statements_core.jsonl")
    Assert-Entry $zip @("knowledge_base/topic_knowledge/article_index.jsonl", "knowledge_base\topic_knowledge\article_index.jsonl")

    $pydCount = ($zip.Entries | Where-Object { $_.FullName -like "*.pyd" }).Count
    $pycacheCount = ($zip.Entries | Where-Object { $_.FullName -like "*__pycache__*" -or $_.FullName -like "*.pyc" }).Count
    if ($pydCount -gt 0) {
        throw "Package check failed. Windows .pyd files found: $pydCount"
    }
    if ($pycacheCount -gt 0) {
        throw "Package check failed. __pycache__ or .pyc files found: $pycacheCount"
    }

    $rawBytes = ($zip.Entries | Measure-Object Length -Sum).Sum
    $zipBytes = ($zip.Entries | Measure-Object CompressedLength -Sum).Sum
    $soCount = ($zip.Entries | Where-Object { $_.FullName -like "*.so" }).Count
    $summary = [pscustomobject]@{
        OutputZip = $OutputZip
        Entries = $zip.Entries.Count
        RawMB = [math]::Round($rawBytes / 1MB, 2)
        ZipMB = [math]::Round($zipBytes / 1MB, 2)
        LinuxSoFiles = $soCount
        WindowsPydFiles = $pydCount
    }
    $summary | Format-List
}
finally {
    $zip.Dispose()
}
