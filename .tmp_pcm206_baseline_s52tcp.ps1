# PCM-20.6 baseline - s52 TCP port probes (read-only, no packets beyond connect attempt)
$hosts = @{ "s52" = "172.20.1.52"; "s113" = "172.20.1.113"; "s117" = "172.20.1.117" }
foreach ($h in $hosts.Keys | Sort-Object) {
    $ip = $hosts[$h]
    foreach ($p in @((22),(2222),(443),(80),(4000),(5055))) {
        $c = New-Object Net.Sockets.TcpClient
        $t = $c.BeginConnect($ip, $p, $null, $null)
        $ok = $t.AsyncWaitHandle.WaitOne(5000)
        if ($ok -and $c.Connected) { $st = "OPEN" } else { $st = "TIMEOUT/CLOSED" }
        Write-Output ("{0} {1}:{2} = {3}" -f $h, $ip, $p, $st)
        try { $c.Close() } catch {}
    }
    Write-Output ""
}
