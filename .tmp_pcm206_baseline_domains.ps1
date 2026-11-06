# PCM-20.6 baseline - TLS cert inspection (read-only)
$domains = @("tasnim.ai.ismc.ir", "rag.ai.ismc.ir", "docs.ai.ismc.ir")
foreach ($d in $domains) {
    Write-Output "=== $d :443 ==="
    try {
        $tcp = New-Object System.Net.Sockets.TcpClient($d, 443)
        $tcp.ReceiveTimeout = 15000
        $ssl = New-Object System.Net.Security.SslStream($tcp.GetStream(), $false, { param($s,$c,$e,$a) $true })
        try {
            $ssl.AuthenticateAsClient($d)
            $cert = New-Object System.Security.Cryptography.X509Certificates.X509Certificate2($ssl.RemoteCertificate)
            Write-Output ("Subject   : " + $cert.Subject)
            Write-Output ("Issuer    : " + $cert.Issuer)
            Write-Output ("NotAfter  : " + $cert.GetExpirationDateString())
            Write-Output ("Thumbprint: " + $cert.Thumbprint)
        } catch [System.Net.Security.AuthenticationException] {
            Write-Output ("AUTH-FAIL : " + $_.Exception.Message)
            try {
                $cert = New-Object System.Security.Cryptography.X509Certificates.X509Certificate2($_.Exception.Certificate)
                Write-Output ("Subject   : " + $cert.Subject)
                Write-Output ("Issuer    : " + $cert.Issuer)
                Write-Output ("NotAfter  : " + $cert.GetExpirationDateString())
                Write-Output ("Thumbprint: " + $cert.Thumbprint)
            } catch { Write-Output "cert-not-obtained" }
        } finally {
            $ssl.Dispose(); $tcp.Close()
        }
    } catch {
        Write-Output ("TCP-FAIL  : " + $_.Exception.Message)
    }
    Write-Output ""
}
