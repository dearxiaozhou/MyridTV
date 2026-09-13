function Resolve-MyridSignTool {
    param(
        [string]$SignToolPath = ''
    )

    if (![string]::IsNullOrWhiteSpace($SignToolPath)) {
        $fullPath = [System.IO.Path]::GetFullPath($SignToolPath)
        if (Test-Path -LiteralPath $fullPath) {
            return $fullPath
        }

        throw "signtool.exe not found: $fullPath"
    }

    $command = Get-Command signtool.exe -ErrorAction SilentlyContinue
    if ($command -and $command.Source -and (Test-Path -LiteralPath $command.Source)) {
        return $command.Source
    }

    $candidates = @(
        'C:\Program Files (x86)\Windows Kits\10\bin\x64\signtool.exe',
        'C:\Program Files (x86)\Windows Kits\10\bin\10.0.26100.0\x64\signtool.exe',
        'C:\Program Files (x86)\Windows Kits\10\bin\10.0.22621.0\x64\signtool.exe',
        'C:\Program Files (x86)\Windows Kits\10\bin\10.0.19041.0\x64\signtool.exe'
    )

    $sdkBin = 'C:\Program Files (x86)\Windows Kits\10\bin'
    if (Test-Path -LiteralPath $sdkBin) {
        $sdkTools = Get-ChildItem -LiteralPath $sdkBin -Directory -ErrorAction SilentlyContinue |
            Sort-Object Name -Descending |
            ForEach-Object { Join-Path $_.FullName 'x64\signtool.exe' }
        $candidates += $sdkTools
    }

    foreach ($candidate in ($candidates | Select-Object -Unique)) {
        if ($candidate -and (Test-Path -LiteralPath $candidate)) {
            return $candidate
        }
    }

    throw 'signtool.exe not found. Install Windows SDK or pass -SignToolPath.'
}

function Test-MyridSigningRequested {
    param(
        [bool]$Sign = $false,
        [string]$CertificatePath = '',
        [string]$CertificateThumbprint = ''
    )

    return (
        $Sign -or
        ![string]::IsNullOrWhiteSpace($CertificatePath) -or
        ![string]::IsNullOrWhiteSpace($CertificateThumbprint)
    )
}

function Get-MyridCertificatePassword {
    param(
        [string]$CertificatePassword = '',
        [string]$CertificatePasswordEnv = 'MYRIDTV_SIGN_CERT_PASSWORD'
    )

    if (![string]::IsNullOrEmpty($CertificatePassword)) {
        return $CertificatePassword
    }

    if (![string]::IsNullOrWhiteSpace($CertificatePasswordEnv)) {
        return [Environment]::GetEnvironmentVariable($CertificatePasswordEnv)
    }

    return ''
}

function Invoke-MyridCodeSign {
    param(
        [Parameter(Mandatory = $true)]
        [string[]]$Files,

        [bool]$Sign = $false,
        [string]$SignToolPath = '',
        [string]$CertificatePath = '',
        [string]$CertificatePassword = '',
        [string]$CertificatePasswordEnv = 'MYRIDTV_SIGN_CERT_PASSWORD',
        [string]$CertificateThumbprint = '',
        [ValidateSet('CurrentUser', 'LocalMachine')]
        [string]$CertificateStoreLocation = 'CurrentUser',
        [string]$TimestampUrl = 'http://timestamp.digicert.com'
    )

    if (!(Test-MyridSigningRequested -Sign $Sign -CertificatePath $CertificatePath -CertificateThumbprint $CertificateThumbprint)) {
        Write-Host 'Code signing: skipped. Pass -Sign, -SignCertPath, or -SignCertThumbprint to enable.'
        return
    }

    $signtool = Resolve-MyridSignTool -SignToolPath $SignToolPath
    $password = Get-MyridCertificatePassword -CertificatePassword $CertificatePassword -CertificatePasswordEnv $CertificatePasswordEnv

    foreach ($file in $Files) {
        if (!(Test-Path -LiteralPath $file)) {
            throw "Cannot sign missing file: $file"
        }

        $args = @('sign', '/fd', 'SHA256')

        if (![string]::IsNullOrWhiteSpace($TimestampUrl)) {
            $args += @('/tr', $TimestampUrl, '/td', 'SHA256')
        }

        if (![string]::IsNullOrWhiteSpace($CertificatePath)) {
            $certFullPath = [System.IO.Path]::GetFullPath($CertificatePath)
            if (!(Test-Path -LiteralPath $certFullPath)) {
                throw "Signing certificate not found: $certFullPath"
            }

            $args += @('/f', $certFullPath)
            if (![string]::IsNullOrEmpty($password)) {
                $args += @('/p', $password)
            }
        }
        elseif (![string]::IsNullOrWhiteSpace($CertificateThumbprint)) {
            if ($CertificateStoreLocation -eq 'LocalMachine') {
                $args += '/sm'
            }
            $args += @('/sha1', $CertificateThumbprint)
        }
        else {
            if ($CertificateStoreLocation -eq 'LocalMachine') {
                $args += '/sm'
            }
            $args += '/a'
        }

        $args += $file

        Write-Host "Code signing: $file"
        & $signtool @args
        if ($LASTEXITCODE -ne 0) {
            throw "signtool failed for: $file"
        }

        $signature = Get-AuthenticodeSignature -LiteralPath $file
        if ($signature.Status -eq 'NotSigned') {
            throw "signtool completed but file is not signed: $file"
        }

        Write-Host "Signature status: $($signature.Status)"
    }
}
