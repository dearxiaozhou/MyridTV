# MyridTV code signing

The release scripts can sign the staged application executables and the final Inno Setup installer.

Signed files:

- `build\MyridTV\MyridTV.exe`
- `build\MyridTV\MyridTV-Desktop.exe`
- `build\installer\MyridTV-Setup.exe`

## First-time checklist

1. Buy or obtain a real OV or EV code-signing certificate from a trusted CA.
2. Export/download it as a PFX, or install it into Windows Certificate Manager with the private key.
3. Run `.\check-signing-prereqs.ps1` to confirm `signtool.exe` and the certificate are available.
4. Build with `.\build-installer.ps1 -Sign ...`.
5. Verify with `.\verify-signatures.ps1 -RequireSigned`.

Self-signed certificates are useful only for local testing. They do not remove Unknown Publisher warnings for other users.

## PFX certificate

Set the PFX password in an environment variable so it is not written into command history:

```powershell
$env:MYRIDTV_SIGN_CERT_PASSWORD = 'your-pfx-password'

.\check-signing-prereqs.ps1 `
  -SignCertPath 'D:\certs\myridtv-code-signing.pfx'

.\build-installer.ps1 `
  -PythonDir 'C:\Users\<user>\AppData\Local\Programs\Python\Python313' `
  -Sign `
  -SignCertPath 'D:\certs\myridtv-code-signing.pfx'
```

## Current user certificate store

If the code-signing certificate is installed in the current user's personal certificate store:

```powershell
.\check-signing-prereqs.ps1 `
  -SignCertThumbprint 'YOUR_CERT_THUMBPRINT'

.\build-installer.ps1 `
  -PythonDir 'C:\Users\<user>\AppData\Local\Programs\Python\Python313' `
  -Sign `
  -SignCertThumbprint 'YOUR_CERT_THUMBPRINT'
```

## Local machine certificate store

If the certificate is installed under `LocalMachine\My`, add `-SignCertStoreLocation LocalMachine`:

```powershell
.\check-signing-prereqs.ps1 `
  -SignCertStoreLocation LocalMachine `
  -SignCertThumbprint 'YOUR_CERT_THUMBPRINT'

.\build-installer.ps1 `
  -PythonDir 'C:\Users\<user>\AppData\Local\Programs\Python\Python313' `
  -Sign `
  -SignCertStoreLocation LocalMachine `
  -SignCertThumbprint 'YOUR_CERT_THUMBPRINT'
```

If `-Sign` is provided without `-SignCertPath` or `-SignCertThumbprint`, `signtool` uses `/a` to auto-select a suitable installed code-signing certificate.

## Optional parameters

- `-SignToolPath`: explicit path to `signtool.exe`
- `-SignTimestampUrl`: timestamp server, defaults to `http://timestamp.digicert.com`
- `-SignCertPasswordEnv`: password environment variable name, defaults to `MYRIDTV_SIGN_CERT_PASSWORD`
- `-SignCertStoreLocation`: `CurrentUser` or `LocalMachine`, defaults to `CurrentUser`

Without `-Sign`, `-SignCertPath`, or `-SignCertThumbprint`, signing is skipped and the package is still built.

## Verify signatures

```powershell
.\verify-signatures.ps1
.\verify-signatures.ps1 -RequireSigned
```

`Valid` means Windows trusts the signature chain on the current machine. `NotSigned` means no signature is present.
