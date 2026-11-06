foreach ($r in @('pcm20_4', 'pcm20_5', 'pcm20_5_crossroot')) {
    $path = "data\tasnim\$r\manifests\registry.json"
    $j = Get-Content -Raw $path | ConvertFrom-Json
    $props = @($j.PSObject.Properties | Where-Object { $_.Name -notin @('schema', 'updated_at', 'created_at') })
    Write-Output ("{0} : {1} entries" -f $r, $props.Count)
    $props | ForEach-Object { Write-Output ("  - " + $_.Name) }
}
