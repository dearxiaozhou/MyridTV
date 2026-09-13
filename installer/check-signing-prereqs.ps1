param(
    [string]$SignToolPath = '',
    [string]$SignCertPath = '',
    [string]$SignCertThumbprint = '',
    [ValidateSet('CurrentUser', 'LocalMachine')]
    [string]$SignCertStoreLocation = 'CurrentUser'
)

$ErrorActionPreference = 'Stop'

. (Join-Path $PSScriptRoot 'signing.ps1')

$signtool = Resolve-MyridSignTool -SignToolPath $SignToolPath
Write-Host "signtool.exe: $signtool"
Write-Host ''

if (![string]::IsNullOrWhiteSpace($SignCertPath)) {
    $certFullPath = [System.IO.Path]::GetFullPath($SignCertPath)
    if (!(Test-Path -LiteralPath $certFullPath)) {
        throw "PFX certificate not found: $certFullPath"
    }

    $item = Get-Item -LiteralPath $certFullPath
    [pscustomobject]@{
        Type = 'PFX'
        Path = $item.FullName
        Length = $item.Length
        LastWriteTime = $item.LastWriteTime
    } | Format-List
    Write-Host 'PFX file found. Password is not validated until signing.'
    exit 0
}

$storePath = if ($SignCertStoreLocation -eq 'LocalMachine') {
    'Cert:\LocalMachine\My'
} else {
    'Cert:\CurrentUser\My'
}

$certs = @(Get-ChildItem $storePath -CodeSigningCert -ErrorAction SilentlyContinue |
    Where-Object { $_.HasPrivateKey } |
    Select-Object Subject, Issuer, Thumbprint, NotBefore, NotAfter, HasPrivateKey)

if (![string]::IsNullOrWhiteSpace($SignCertThumbprint)) {
    $match = @($certs | Where-Object { $_.Thumbprint -replace '\s', '' -ieq ($SignCertThumbprint -replace '\s', '') })
    if ($match.Count -eq 0) {
        throw "Code signing certificate with thumbprint '$SignCertThumbprint' was not found in $storePath."
    }

    Write-Host "Matching code signing certificate in ${storePath}:"
    $match | Format-List
    exit 0
}

if ($certs.Count -eq 0) {
    Write-Host "No code signing certificates with private keys were found in $storePath."
    Write-Host 'Use -SignCertPath for a PFX file, or install a real code signing certificate and pass -SignCertThumbprint.'
    exit 1
}

Write-Host "Available code signing certificates in ${storePath}:"
$certs | Format-Table -AutoSize -Wrap
