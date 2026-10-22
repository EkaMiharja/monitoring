<#
.SYNOPSIS
    Mengganti IP VM (variabel VM_HOST atau RF_VM_HOST) di .env lalu memverifikasi konektivitas.

.DESCRIPTION
    Semua URL sumber data memakai ${VM_HOST} (VM lightgbm) atau ${RF_VM_HOST}
    (VM random forest), jadi satu baris di .env adalah satu-satunya tempat IP
    tiap VM ditulis. Script ini mengganti baris tersebut, lalu memeriksa ping,
    endpoint API, dan port iperf3.

    Bila subnet berubah, script mencetak blok aturan ufw yang harus dijalankan
    di kedua VM, karena keduanya memakai subnet jaringan yang sama.

.EXAMPLE
    .\scripts\set_vm_host.ps1 192.168.1.42
    .\scripts\set_vm_host.ps1 -Variable RF_VM_HOST 192.168.1.6
#>
param(
    [Parameter(Mandatory = $true)]
    [string]$Ip,

    [ValidateSet("VM_HOST", "RF_VM_HOST")]
    [string]$Variable = "VM_HOST",

    [string]$ProjectRoot = "",

    [string]$ExpectedSubnet = "192.168.1.0/24"
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
$previousIp = ""
$pattern = "^\s*" + [regex]::Escape($Variable) + "\s*="
for ($i = 0; $i -lt $lines.Count; $i++) {
    if ($lines[$i] -match $pattern) {
        $previousIp = ($lines[$i] -split '=', 2)[1].Trim()
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

function Get-Subnet {
    param([string]$Address)
    $octets = $Address -split '\.'
    return "{0}.{1}.{2}.0/24" -f $octets[0], $octets[1], $octets[2]
}

function Show-UfwCommands {
    param([string]$Subnet, [string]$Label)
    Write-Host "`n$Label" -ForegroundColor Yellow
    foreach ($source in @($Subnet, "192.168.56.0/24", "100.64.0.0/10")) {
        $note = switch -Wildcard ($source) {
            "192.168.56.0/24" { "  # host-only VirtualBox: mesin penyerang + capture IDS" }
            "100.64.0.0/10"   { "  # Tailscale (boleh dihapus setelah Tailscale dinonaktifkan)" }
            default           { "  # jaringan LAN lab" }
        }
        Write-Host "  sudo ufw allow from $source to any port 22    proto tcp$note" -ForegroundColor Yellow
        Write-Host "  sudo ufw allow from $source to any port 8080  proto tcp" -ForegroundColor Yellow
        Write-Host "  sudo ufw allow from $source to any port 61208 proto tcp" -ForegroundColor Yellow
        Write-Host "  sudo ufw allow from $source to any port 5201  proto tcp" -ForegroundColor Yellow
        Write-Host "  sudo ufw allow from $source to any port 5201  proto udp" -ForegroundColor Yellow
    }
}

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

$subnet = Get-Subnet -Address $Ip
$previousSubnet = if ($previousIp -and $previousIp -ne $Ip) { Get-Subnet -Address $previousIp } else { "" }

if ($subnet -ne $ExpectedSubnet) {
    Write-Host "`nSubnet IP VM baru ($subnet) berbeda dari $ExpectedSubnet." -ForegroundColor Yellow
    Show-UfwCommands -Subnet $subnet -Label "Tambahkan rule ufw untuk subnet baru (jalankan di KEDUA VM: lightgbm & random forest):"
    if ($previousSubnet -and $previousSubnet -ne $subnet) {
        Write-Host "`nHapus rule subnet lama ($previousSubnet) (jalankan di kedua VM):" -ForegroundColor Yellow
        Write-Host "  sudo ufw status numbered   # lihat nomor rule" -ForegroundColor Yellow
        Write-Host "  sudo ufw delete <nomor>   # ulangi untuk 5 rule subnet lama" -ForegroundColor Yellow
    }
}
elseif ($previousSubnet) {
    Write-Host "`nSubnet tetap ($subnet); rule ufw di kedua VM tidak perlu diubah." -ForegroundColor Cyan
}

Write-Host "`nRestart dashboard agar .env terbaca ulang." -ForegroundColor Cyan
Write-Host "  Get-CimInstance Win32_Process | Where-Object { `$_.CommandLine -like '*app.py*' } | ForEach-Object { Stop-Process -Id `$_.ProcessId -Force }" -ForegroundColor DarkGray
Write-Host "  Start-Process -FilePath '$env:USERPROFILE\PycharmProjects\Dashboard\.venv\Scripts\python.exe' -ArgumentList 'app.py' -WorkingDirectory '$env:USERPROFILE\PycharmProjects\Dashboard' -WindowStyle Hidden" -ForegroundColor DarkGray
