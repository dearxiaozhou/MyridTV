"""The launcher checks bind permission, not merely whether connect succeeds."""
from pathlib import Path
import subprocess
import unittest


class StartupPortProbe(unittest.TestCase):
    def test_occupied_free_and_released_probe(self):
        script = r'''
$errors=$null; $tokens=$null
$ast=[System.Management.Automation.Language.Parser]::ParseFile($args[0],[ref]$tokens,[ref]$errors)
if($errors.Count){throw 'Startup script parse failed'}
$function=$ast.Find({param($node) $node -is [System.Management.Automation.Language.FunctionDefinitionAst] -and $node.Name -eq 'Test-PortBindable'},$true)
Invoke-Expression $function.Extent.Text
$held=[System.Net.Sockets.TcpListener]::new([System.Net.IPAddress]::Loopback,0)
$held.ExclusiveAddressUse=$true
$held.Start()
$port=([System.Net.IPEndPoint]$held.LocalEndpoint).Port
try { if(Test-PortBindable '127.0.0.1' $port){throw 'Occupied port accepted'} }
finally {$held.Stop()}
if(!(Test-PortBindable '127.0.0.1' $port)){throw 'Free port rejected'}
if(!(Test-PortBindable '127.0.0.1' $port)){throw 'Probe leaked its listener'}
Write-Output 'PASS - occupied, free and released port probes'
'''
        root = Path(__file__).resolve().parents[1]
        # Pass the source path as a script argument without shell interpolation.
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            probe = Path(tmp) / 'probe.ps1'
            probe.write_text(script, encoding='utf-8')
            result = subprocess.run(['powershell','-NoProfile','-ExecutionPolicy','Bypass','-File',str(probe),str(root/'start_myridtv.ps1')],
                                    capture_output=True, text=True, errors='replace')
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)


if __name__ == '__main__':
    unittest.main()
