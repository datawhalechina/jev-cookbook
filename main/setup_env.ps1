# Windows setup. ASCII comments also support Windows PowerShell 5 without a BOM.
param([string]$TorchBackend = $(if ($env:JEV_TORCH_BACKEND) { $env:JEV_TORCH_BACKEND } else { "auto" }))
$ErrorActionPreference = "Stop"
$ProjectRoot = $PSScriptRoot
$LocalRequirements = Join-Path $ProjectRoot "LocalJev\requirements-local.txt"
Set-Location -LiteralPath $ProjectRoot

function Invoke-Checked {
    param([string]$Executable, [string[]]$CommandArgs)
    & $Executable @CommandArgs
    if ($LASTEXITCODE -ne 0) { throw "$Executable failed (exit $LASTEXITCODE)." }
}

$ProjectPython = Join-Path $ProjectRoot ".venv\Scripts\python.exe"
if (Get-Command uv -ErrorAction SilentlyContinue) {
    if (-not (Test-Path -LiteralPath $ProjectPython)) {
        Invoke-Checked uv @("venv", ".venv", "--python", "3.12")
    }
    Invoke-Checked uv @("pip", "install", "--python", $ProjectPython, "pip", "-r", $LocalRequirements, "--torch-backend", $TorchBackend)
} else {
    if (-not (Test-Path -LiteralPath $ProjectPython)) {
        if (Get-Command py -ErrorAction SilentlyContinue) {
            $SelectedVersion = $null
            foreach ($CandidateVersion in @("-3.12", "-3.11", "-3.10")) {
                & py $CandidateVersion -c "import sys" 2>$null
                if ($LASTEXITCODE -eq 0) { $SelectedVersion = $CandidateVersion; break }
            }
            if (-not $SelectedVersion) { throw "Install uv or Python 3.10-3.12 first." }
            Invoke-Checked py @($SelectedVersion, "-m", "venv", ".venv")
        } elseif (Get-Command python -ErrorAction SilentlyContinue) {
            Invoke-Checked python @("-c", "import sys; assert (3,10) <= sys.version_info[:2] <= (3,12), 'Install Python 3.12 or uv first.'")
            Invoke-Checked python @("-m", "venv", ".venv")
        } else { throw "Install uv or Python 3.12 first." }
    }
    Invoke-Checked $ProjectPython @("-m", "pip", "install", "--upgrade", "pip")
    Invoke-Checked $ProjectPython @("-m", "pip", "install", "-r", $LocalRequirements)
}
Invoke-Checked $ProjectPython @("-m", "pip", "check")
Invoke-Checked $ProjectPython @("-m", "ipykernel", "install", "--sys-prefix", "--name", "python3", "--display-name", "Python (jevbook)")
Invoke-Checked $ProjectPython @("-c", "import torch; print('PyTorch:', torch.__version__, 'CUDA:', torch.cuda.is_available())")
Write-Host ""
Write-Host "Ready. Start Jupyter from main:"
Write-Host "  .\.venv\Scripts\python.exe -m jupyterlab LocalJev\LocalJev.ipynb"
Write-Host "Run All LocalJev, keep its kernel running, then Run All chapter 1-5 notebooks. No remote TypeSafe API key required."
