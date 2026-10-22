# DEPRECATED: tunnel SSH tidak dipakai lagi.
# Kedua VM (lightgbm 192.168.1.7 dan random forest 192.168.1.6) kini diakses
# langsung lewat jaringan lab: API di :8080, Glances di :61208, iperf3 di :5201
# (semua bind 0.0.0.0, firewall ufw dibatasi per subnet).
# Scheduled Task "SSH Sentinel Tunnel" sudah dinonaktifkan.
# Script ini disimpan sebagai referensi/backup bila ada kebutuhan akses via tunnel.
$ErrorActionPreference = "Stop"

$ssh = Join-Path $env:WINDIR "System32\OpenSSH\ssh.exe"
$key = "C:\Users\eka\.ssh\ids_audit"
$server = "server@10.207.241.187"
$localGlances = 61210
$localApi = 18080
$logOut = Join-Path $env:TEMP "ssh-sentinel-tunnel.out"
$logErr = Join-Path $env:TEMP "ssh-sentinel-tunnel.err"

function Test-LocalPort([int]$port) {
    $client = [System.Net.Sockets.TcpClient]::new()
    try {
        $client.Connect("127.0.0.1", $port)
        return $true
    }
    catch {
        return $false
    }
    finally {
        $client.Dispose()
    }
}

function Stop-SentinelTunnel {
    Get-CimInstance Win32_Process -Filter "Name='ssh.exe'" |
        Where-Object {
            $_.CommandLine -like "*$localApi`:127.0.0.1:8080*" -and
            $_.CommandLine -like "*$server*"
        } |
        ForEach-Object {
            Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue
        }
}

if (-not (Test-Path $ssh)) {
    Write-Output "ssh.exe tidak ditemukan: $ssh"
    exit 1
}
if (-not (Test-Path $key)) {
    Write-Output "SSH key tidak ditemukan: $key"
    exit 1
}

if ((Test-LocalPort $localGlances) -and (Test-LocalPort $localApi)) {
    Write-Output "Tunnel sudah aktif."
    exit 0
}

for ($attempt = 1; $attempt -le 3; $attempt++) {
    if ((Test-LocalPort $localGlances) -and (Test-LocalPort $localApi)) {
        Write-Output "Tunnel sudah aktif."
        exit 0
    }

    Stop-SentinelTunnel
    Start-Sleep -Seconds 1

    $arguments = @(
        "-N",
        "-i", $key,
        "-o", "BatchMode=yes",
        "-o", "ConnectTimeout=8",
        "-o", "ExitOnForwardFailure=yes",
        "-o", "ServerAliveInterval=30",
        "-o", "ServerAliveCountMax=3",
        "-o", "StrictHostKeyChecking=no",
        "-o", "UserKnownHostsFile=NUL",
        "-L", "127.0.0.1:$localGlances`:127.0.0.1:61208",
        "-L", "127.0.0.1:$localApi`:127.0.0.1:8080",
        $server
    )

    Start-Process -FilePath $ssh -ArgumentList $arguments -WindowStyle Hidden `
        -RedirectStandardOutput $logOut -RedirectStandardError $logErr
    Start-Sleep -Seconds 2

    if ((Test-LocalPort $localGlances) -and (Test-LocalPort $localApi)) {
        Write-Output "Tunnel aktif (percobaan $attempt)."
        exit 0
    }

    Write-Output "Percobaan $attempt gagal, mencoba lagi."
}

Write-Output "Tunnel gagal dimulai. Periksa $logErr."
exit 1
