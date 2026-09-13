param(
    [string[]]$Files = @(
        (Join-Path $PSScriptRoot 'build\MyridTV\MyridTV.exe'),
        (Join-Path $PSScriptRoot 'build\MyridTV\MyridTV-Desktop.exe'),
        (Join-Path $PSScriptRoot 'build\installer\MyridTV-Setup.exe')
    ),

    [switch]$RequireSigned
)

$ErrorActionPreference = 'Stop'

$results = foreach ($file in $Files) {
    $fullPath = [System.IO.Path]::GetFullPath($file)
    if (!(Test-Path -LiteralPath $fullPath)) {
        [pscustomobject]@{
            File = $fullPath
            Status = 'Missing'
            Subject = ''
            Thumbprint = ''
            NotAfter = ''
            Message = 'File does not exist.'
        }
        continue
    }

    $signature = Get-AuthenticodeSignature -LiteralPath $fullPath
    [pscustomobject]@{
        File = $fullPath
        Status = $signature.Status
        Subject = if ($signature.SignerCertificate) { $signature.SignerCertificate.Subject } else { '' }
        Thumbprint = if ($signature.SignerCertificate) { $signature.SignerCertificate.Thumbprint } else { '' }
        NotAfter = if ($signature.SignerCertificate) { $signature.SignerCertificate.NotAfter } else { '' }
        Message = $signature.StatusMessage
    }
}

$results | Format-Table File, Status, Subject, Thumbprint, NotAfter -AutoSize -Wrap

if ($RequireSigned) {
    $failed = @($results | Where-Object { $_.Status -ne 'Valid' })
    if ($failed.Count -gt 0) {
        Write-Error "Signature verification failed for $($failed.Count) file(s)."
        exit 1
    }
}
