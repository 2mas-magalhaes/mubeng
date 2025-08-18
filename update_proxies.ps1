# --- CONFIGURAÇÃO ---
$headers = @{ "User-Agent" = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/108.0.0.0 Safari/537.36" }

$proxySources = @{
    "http" = @(
        "https://api.proxyscrape.com/v2/?request=displayproxies&protocol=http", "https://raw.githubusercontent.com/zloi-user/hideip.me/main/http.txt",
        "https://raw.githubusercontent.com/zloi-user/hideip.me/main/https.txt", "https://raw.githubusercontent.com/BreakingTechFr/Proxy_Free/main/proxies/http.txt",
        "https://raw.githubusercontent.com/ErcinDedeoglu/proxies/main/proxies/http.txt", "https://raw.githubusercontent.com/ErcinDedeoglu/proxies/main/proxies/https.txt",
        "https://raw.githubusercontent.com/proxifly/free-proxy-list/main/proxies/protocols/http/data.txt", "https://yakumo.rei.my.id/HTTP",
        "https://raw.githubusercontent.com/vakhov/fresh-proxy-list/master/http.txt", "https://raw.githubusercontent.com/vakhov/fresh-proxy-list/master/https.txt",
        "https://raw.githubusercontent.com/officialputuid/KangProxy/KangProxy/http/http.txt", "https://raw.githubusercontent.com/officialputuid/KangProxy/KangProxy/https/https.txt",
        "https://sunny9577.github.io/proxy-scraper/generated/http_proxies.txt", "https://raw.githubusercontent.com/TheSpeedX/SOCKS-List/master/http.txt"
    ); "socks4" = @(
        "https://api.proxyscrape.com/v2/?request=displayproxies&protocol=socks4", "https://raw.githubusercontent.com/zloi-user/hideip.me/main/socks4.txt",
        "https://raw.githubusercontent.com/BreakingTechFr/Proxy_Free/main/proxies/socks4.txt", "https://raw.githubusercontent.com/ErcinDedeoglu/proxies/main/proxies/socks4.txt",
        "https://raw.githubusercontent.com/proxifly/free-proxy-list/main/proxies/protocols/socks4/data.txt", "https://yakumo.rei.my.id/SOCKS4",
        "https://raw.githubusercontent.com/vakhov/fresh-proxy-list/master/socks4.txt", "https://raw.githubusercontent.com/officialputuid/KangProxy/KangProxy/socks4/socks4.txt",
        "https://sunny9577.github.io/proxy-scraper/generated/socks4_proxies.txt", "https://raw.githubusercontent.com/TheSpeedX/SOCKS-List/master/socks4.txt"
    ); "socks5" = @(
        "https://api.proxyscrape.com/v2/?request=displayproxies&protocol=socks5", "https://raw.githubusercontent.com/zloi-user/hideip.me/main/socks5.txt",
        "https://raw.githubusercontent.com/hookzof/socks5_list/master/proxy.txt", "https://raw.githubusercontent.com/BreakingTechFr/Proxy_Free/main/proxies/socks5.txt",
        "https://raw.githubusercontent.com/ErcinDedeoglu/proxies/main/proxies/socks5.txt", "https://raw.githubusercontent.com/proxifly/free-proxy-list/main/proxies/protocols/socks5/data.txt",
        "https://yakumo.rei.my.id/SOCKS5", "https://raw.githubusercontent.com/vakhov/fresh-proxy-list/master/socks5.txt",
        "https://raw.githubusercontent.com/officialputuid/KangProxy/KangProxy/socks5/socks5.txt",
        "https://sunny9577.github.io/proxy-scraper/generated/socks5_proxies.txt", "https://raw.githubusercontent.com/TheSpeedX/SOCKS-List/master/socks5.txt"
    )
}

$downloadThreadCount = 5
$liveFile = "live.txt"
$tempLiveFile = "live_temp.txt"

Write-Host "A iniciar o script de atualização de proxies..." -ForegroundColor Green

# --- INICIALIZAÇÃO ---
$existingProxies = [System.Collections.Generic.HashSet[string]]::new([System.StringComparer]::OrdinalIgnoreCase)
if (Test-Path $liveFile) {
    Get-Content $liveFile | ForEach-Object { $existingProxies.Add($_) > $null }
}
Write-Host "[$((Get-Date).ToString("HH:mm:ss"))] Carregados $($existingProxies.Count) proxies existentes do '$liveFile'."

# --- LOOP INFINITO ---
while ($true) {
    try {
        $timestamp = Get-Date -Format "HH:mm:ss"
        $allProxies = [System.Collections.Concurrent.ConcurrentBag[string]]::new()

        # --- FASE 1: RECOLHA RÁPIDA DE PROXIES (PARALELA) ---
        Write-Host "[$timestamp] A recolher novas fontes de proxies..."
        
        $downloadScriptBlock = { param($url, $protocol, $headers); try { $response = Invoke-WebRequest -Uri $url -UseBasicParsing -Headers $headers -TimeoutSec 20; return $response.Content.Split([Environment]::NewLine) | Where-Object { $_.Trim() -ne "" } } catch {}; return $null }
        $downloadPool = [System.Management.Automation.Runspaces.RunspaceFactory]::CreateRunspacePool(1, $downloadThreadCount); $downloadPool.Open()
        $downloadJobs = [System.Collections.Generic.List[object]]::new()
        foreach ($protocol in $proxySources.Keys) { foreach ($url in $proxySources[$protocol]) { $ps = [System.Management.Automation.PowerShell]::Create(); $ps.RunspacePool = $downloadPool; $ps.AddScript($downloadScriptBlock).AddArgument($url).AddArgument($protocol).AddArgument($headers) | Out-Null; $jobInfo = [PSCustomObject]@{ Instance = $ps; Handle = $ps.BeginInvoke(); Protocol = $protocol }; $downloadJobs.Add($jobInfo) } }
        foreach ($job in $downloadJobs) { $proxiesFromJob = $job.Instance.EndInvoke($job.Handle); if ($proxiesFromJob) { foreach ($proxy in $proxiesFromJob) { $formattedProxy = $proxy.Trim(); if ($job.Protocol -ne "http" -and $formattedProxy -notlike "*://*") { $allProxies.Add("$($job.Protocol)://$formattedProxy") } else { $allProxies.Add($formattedProxy) } } }; $job.Instance.Dispose() }
        $downloadPool.Close(); $downloadPool.Dispose()
        
        $newUniqueProxies = $allProxies.ToArray() | Where-Object { -not $existingProxies.Contains($_) } | Sort-Object -Unique
        Write-Host "[$timestamp] Recolha concluída. Encontrados $($newUniqueProxies.Count) proxies novos para verificar."

        # --- FASE 2: VERIFICAÇÃO E ADIÇÃO ---
        if ($newUniqueProxies.Count -gt 0) {
            $newUniqueProxies | Out-File -FilePath "proxies_to_check.txt" -Encoding utf8
            if (Test-Path $tempLiveFile) { Remove-Item $tempLiveFile }
            Write-Host "[$timestamp] A verificar os proxies novos (timeout de 1500ms)..."
            
            mubeng -f "proxies_to_check.txt" -c -o $tempLiveFile --timeout 1500ms

            if (Test-Path $tempLiveFile) {
                $validatedProxies = Get-Content $tempLiveFile
                
                # (A CORREÇÃO) Usa Add-Content para adicionar os novos proxies ao ficheiro principal
                Add-Content -Path $liveFile -Value $validatedProxies
                
                # Atualiza o HashSet na memória
                $validatedProxies | ForEach-Object { $existingProxies.Add($_) > $null }
                
                $countAdded = $validatedProxies.Count
                Write-Host "[$timestamp] Verificação concluída. Adicionados $countAdded proxies novos ao '$liveFile'." -ForegroundColor Green
            } else {
                Write-Host "[$timestamp] Verificação concluída. Nenhum proxy novo passou na verificação." -ForegroundColor Yellow
            }
        }

        Write-Host "[$timestamp] Total de proxies em '$liveFile': $($existingProxies.Count)." -ForegroundColor Cyan

    } catch {
        Write-Host "[$timestamp] Ocorreu um erro geral no script: $($_.Exception.Message)" -ForegroundColor Red
    }

    # --- ESPERAR ---
    Write-Host "A aguardar 1 segundo para o próximo ciclo..."
    Start-Sleep -Seconds 1
}