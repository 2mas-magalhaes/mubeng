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
        "https://raw.githubusercontent.com/officialputuid/KangProxy/KangProxy/socks5/socks5.txt", "https://sunny9577.github.io/proxy-scraper/generated/socks5_proxies.txt",
        "https://raw.githubusercontent.com/TheSpeedX/SOCKS-List/master/socks5.txt"
    )
}

$downloadThreadCount = 5
$liveFile = "live.txt"
$combinedFile = "proxies_combined.txt"

Write-Host "A iniciar o script de atualização de proxies..." -ForegroundColor Green

# --- LOOP INFINITO ---
while ($true) {
    try {
        $timestamp = Get-Date -Format "HH:mm:ss"
        $allProxies = [System.Collections.Concurrent.ConcurrentBag[string]]::new()

        # --- FASE 1: RECOLHA RÁPIDA DE PROXIES (PARALELA) ---
        Write-Host "[$timestamp] A recolher proxies de $($proxySources.Keys.Count) tipos de fontes..."
        
        $downloadScriptBlock = {
            param($url, $protocol, $headers)
            try {
                $response = Invoke-WebRequest -Uri $url -UseBasicParsing -Headers $headers -TimeoutSec 20
                # Retorna uma lista de strings limpas
                return $response.Content.Split([Environment]::NewLine) | Where-Object { $_.Trim() -ne "" }
            } catch {}
            return $null
        }

        $downloadPool = [System.Management.Automation.Runspaces.RunspaceFactory]::CreateRunspacePool(1, $downloadThreadCount)
        $downloadPool.Open()
        $downloadJobs = New-Object System.Collections.Generic.List[object]

        foreach ($protocol in $proxySources.Keys) {
            foreach ($url in $proxySources[$protocol]) {
                $ps = [System.Management.Automation.PowerShell]::Create()
                $ps.RunspacePool = $downloadPool
                $ps.AddScript($downloadScriptBlock).AddArgument($url).AddArgument($protocol).AddArgument($headers) | Out-Null
                $jobInfo = [PSCustomObject]@{ Instance = $ps; Handle = $ps.BeginInvoke(); Protocol = $protocol }
                $downloadJobs.Add($jobInfo)
            }
        }
        
        Write-Host "[$timestamp] A executar $($downloadJobs.Count) downloads em paralelo..."
        foreach ($job in $downloadJobs) {
            $proxiesFromJob = $job.Instance.EndInvoke($job.Handle)
            if ($proxiesFromJob) {
                # (A CORREÇÃO) Adiciona o prefixo de protocolo aqui, depois de receber os resultados
                foreach ($proxy in $proxiesFromJob) {
                    $formattedProxy = $proxy.Trim()
                    if ($job.Protocol -ne "http" -and $formattedProxy -notlike "*://*") {
                        $allProxies.Add("$($job.Protocol)://$formattedProxy")
                    } else {
                        $allProxies.Add($formattedProxy)
                    }
                }
            }
            $job.Instance.Dispose()
        }
        $downloadPool.Close(); $downloadPool.Dispose()

        $uniqueProxies = $allProxies.ToArray() | Sort-Object -Unique
        Write-Host "[$timestamp] Downloads concluídos. Obtidos $($uniqueProxies.Count) proxies únicos."

        # --- FASE 2: VERIFICAÇÃO EM BLOCO (MÉTODO FIÁVEL) ---
        if (Test-Path $combinedFile) { Remove-Item $combinedFile }
        $uniqueProxies | Out-File -FilePath $combinedFile -Encoding utf8
        
        if (Test-Path $liveFile) { Remove-Item $liveFile }
        Write-Host "[$timestamp] A verificar $($uniqueProxies.Count) proxies (timeout de 1200ms)..."
        
        # Usa o mubeng para verificar a lista completa de uma só vez
        mubeng -f $combinedFile -c -o $liveFile --timeout 1200ms

        if (Test-Path $liveFile) {
            $lineCount = (Get-Content $liveFile | Measure-Object -Line).Lines
            Write-Host "[$timestamp] Verificação completa. $lineCount proxies rápidos guardados em '$live.txt'." -ForegroundColor Green
        } else {
            Write-Host "[$timestamp] Verificação completa. Nenhum proxy rápido foi encontrado." -ForegroundColor Yellow
        }

    } catch {
        Write-Host "[$timestamp] Ocorreu um erro geral no script: $($_.Exception.Message)" -ForegroundColor Red
    }

    # --- ESPERAR ---
    Write-Host "A aguardar 1 segundos para o próximo ciclo..."
    Start-Sleep -Seconds 1
}