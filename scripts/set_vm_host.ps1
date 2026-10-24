<#
.SYNOPSIS
    Mengganti IP VM (variabel VM_HOST, RF_VM_HOST, atau FAIL2BAN_VM_HOST) di .env lalu memverifikasi konektivitas.

.DESCRIPTION
    Semua URL sumber data memakai ${VM_HOST} (VM lightgbm), ${RF_VM_HOST}
    (VM random forest), atau ${FAIL2BAN_VM_HOST} (VM fail2ban), jadi satu baris
    di .env adalah satu-satunya tempat IP tiap VM ditulis. Script ini mengganti
    baris tersebut, lalu memeriksa ping, endpoint API, dan port iperf3. IP laptop
    tidak disimpan di konfigurasi,
    jadi perubahan IP laptop akibat DHCP tidak perlu menjalankan script ini.

    Firewall VM tidak dipakai (ufw nonaktif), sehingga perubahan IP atau subnet
    tidak memerlukan rule tambahan.

.EXAMPLE
    .\scripts\set_vm_host.ps1 192.168.100.69
    .\scripts\set_vm_host.ps1 -Variable RF_VM_HOST 192.168.100.70
    .\scripts\set_vm_host.ps1 -Variable FAIL2BAN_VM_HOST 192.168.100.71
#>
param(
    [Parameter(Mandatory = $true)]
    [string]$Ip,

    [ValidateSet("VM_HOST", "RF_VM_HOST", "FAIL2BAN_VM_HOST")]
    [string]$Variable = "VM_HOST",

    [string]$ProjectRoot = ""
)

$ErrorActionPreference = "Stop"

if (-not $ProjectRoot) {
    $scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
    $ProjectRoot = Split-Path -Parent $scriptDir
}

$envFile = Join-Path $ProjectRoot ".env"
if (-not (Test-Path $envFile)) {
    throw "File .env tidak ditemukan: $envFile"
}

$parsed = $null
if (-not [System.Net.IPAddress]::TryParse($Ip, [ref]$parsed)) {
    throw "IP tidak valid: $Ip"
}

$lines = [System.Collections.Generic.List[string]](Get-Content -LiteralPath $envFile)
$updated = $false
$pattern = "^\s*" + [regex]::Escape($Variable) + "\s*="
for ($i = 0; $i -lt $lines.Count; $i++) {
    if ($lines[$i] -match $pattern) {
        $lines[$i] = "$Variable=$Ip"
        $updated = $true
    }
}
if (-not $updated) {
    $lines.Insert(0, "$Variable=$Ip")
}
# UTF-8 tanpa BOM supaya python-dotenv tidak salah baca baris pertama.
[System.IO.File]::WriteAllLines($envFile, $lines)
Write-Host "$Variable di .env -> $Ip" -ForegroundColor Green

function Test-TcpPort {
    param([string]$Target, [int]$Port, [int]$TimeoutMs = 3000)
    $client = New-Object System.Net.Sockets.TcpClient
    try {
        $async = $client.BeginConnect($Target, $Port, $null, $null)
        if ($async.AsyncWaitHandle.WaitOne($TimeoutMs)) {
            $client.EndConnect($async)
            return $true
        }
        return $false
    }
    catch {
        return $false
    }
    finally {
        $client.Close()
    }
}

function Test-TcpPortReliable {
    param([string]$Target, [int]$Port, [int]$Attempts = 3)
    for ($i = 0; $i -lt $Attempts; $i++) {
        if (Test-TcpPort -Target $Target -Port $Port) {
            return $true
        }
        Start-Sleep -Milliseconds 800
    }
    return $false
}

Write-Host "`nCek konektivitas ke $Ip" -ForegroundColor Cyan

$ping = Test-Connection -ComputerName $Ip -Count 2 -ErrorAction SilentlyContinue
if ($ping) {
    $samples = $ping | ForEach-Object {
        if ($_.PSObject.Properties.Name -contains "Latency") { $_.Latency } else { $_.ResponseTime }
    }
    $avg = [math]::Round(($samples | Measure-Object -Average).Average, 2)
    Write-Host ("  ping        : OK (rata-rata {0} ms)" -f $avg)
}
else {
    Write-Host "  ping        : GAGAL" -ForegroundColor Yellow
}

foreach ($port in 8080, 61208, 5201) {
    $state = if (Test-TcpPortReliable -Target $Ip -Port $port) { "OPEN" } else { "TIDAK TERBUKA" }
    $color = if ($state -eq "OPEN") { "Green" } else { "Yellow" }
    Write-Host ("  port {0,-6}: {1}" -f $port, $state) -ForegroundColor $color
}

try {
    $health = Invoke-RestMethod -Uri "http://$Ip`:8080/health" -TimeoutSec 5
    Write-Host ("  /health     : {0}" -f ($health | ConvertTo-Json -Compress)) -ForegroundColor Green
}
catch {
    Write-Host "  /health     : GAGAL ($($_.Exception.Message))" -ForegroundColor Yellow
}

try {
    $quicklook = Invoke-RestMethod -Uri "http://$Ip`:61208/api/4/quicklook" -TimeoutSec 5
    $cpu = ($quicklook.cpu | ConvertTo-Json -Compress)
    $mem = ($quicklook.mem | ConvertTo-Json -Compress)
    Write-Host ("  quicklook   : cpu={0} mem={1}" -f $cpu, $mem) -ForegroundColor Green
}
catch {
    Write-Host "  quicklook   : GAGAL ($($_.Exception.Message))" -ForegroundColor Yellow
}

Write-Host "`nFirewall VM tidak dipakai (ufw nonaktif); tidak ada rule yang perlu diubah." -ForegroundColor Cyan

Write-Host "`nRestart dashboard agar .env terbaca ulang." -ForegroundColor Cyan
Write-Host "  Get-CimInstance Win32_Process | Where-Object { `$_.CommandLine -like '*app.py*' } | ForEach-Object { Stop-Process -Id `$_.ProcessId -Force }" -ForegroundColor DarkGray
Write-Host "  Start-Process -FilePath '$env:USERPROFILE\PycharmProjects\Dashboard\.venv\Scripts\python.exe' -ArgumentList 'app.py' -WorkingDirectory '$env:USERPROFILE\PycharmProjects\Dashboard' -WindowStyle Hidden" -ForegroundColor DarkGray
