param(
    [string]$CredentialFile = (Join-Path (Split-Path -Parent $PSScriptRoot) '192.168.5.42-creds'),
    [string]$ComputerName,
    [string]$RemoteScriptPath = 'C:\Users\sup02\catia-v5-mcp-server\scripts\windows\restart_catia_mcp_in_session.ps1',
    [string]$RemoteRepoPath = 'C:\Users\sup02\catia-v5-mcp-server',
    [string]$RemoteTokenFile = 'C:\Users\sup02\catia-v5-mcp-server\.catia-mcp-env',
    [string]$PythonPath = 'C:\Users\sup02\AppData\Local\Programs\Python\Python311\python.exe',
    [string]$BindHost,
    [int]$Port = 8000,
    [string[]]$AllowedHost,
    [string]$TargetUser = 'sup02',
    [int]$TimeoutSeconds = 45,
    [switch]$DryRun,
    [switch]$SkipUpload,
    [switch]$SkipTokenSync
)

$ErrorActionPreference = 'Stop'

function Read-KeyValueFile {
    param([Parameter(Mandatory = $true)][string]$Path)

    if (-not (Test-Path -LiteralPath $Path -PathType Leaf)) {
        throw "Credential file does not exist: $Path"
    }

    $values = @{}
    Get-Content -LiteralPath $Path | ForEach-Object {
        if ($_ -match '^\s*([^#][^=:]*?)\s*[:=]\s*(.*)$') {
            $values[$matches[1].Trim()] = $matches[2].Trim()
        }
    }

    return $values
}

function New-RequiredCredential {
    param([Parameter(Mandatory = $true)][hashtable]$Values)

    foreach ($key in @('adm_username', 'adm_pass')) {
        if (-not $Values.ContainsKey($key) -or -not $Values[$key]) {
            throw "Credential file is missing required key '$key'."
        }
    }

    $password = ConvertTo-SecureString $Values.adm_pass -AsPlainText -Force
    return [pscredential]::new($Values.adm_username, $password)
}

function Invoke-McpInitializeProbe {
    param(
        [Parameter(Mandatory = $true)][string]$Uri,
        [Parameter(Mandatory = $true)][string]$Token
    )

    $body = '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2024-11-05","capabilities":{},"clientInfo":{"name":"catia-mcp-restart-check","version":"0"}}}'
    $headers = @{
        Authorization = "Bearer $Token"
        Accept = 'application/json, text/event-stream'
    }

    Invoke-WebRequest `
        -Uri $Uri `
        -Method Post `
        -Headers $headers `
        -ContentType 'application/json' `
        -Body $body `
        -UseBasicParsing `
        -TimeoutSec 5
}

$deploy = Read-KeyValueFile -Path $CredentialFile
$credential = New-RequiredCredential -Values $deploy

if (-not $ComputerName) {
    $ComputerName = if ($deploy.Deploy_host) { $deploy.Deploy_host } else { '192.168.5.42' }
}
if (-not $BindHost) {
    $BindHost = $ComputerName
}
if (-not $AllowedHost -or $AllowedHost.Count -eq 0) {
    $AllowedHost = @("$BindHost`:$Port")
}
if (-not $deploy.MCP_TOKEN) {
    throw "Credential file is missing required key 'MCP_TOKEN'."
}

$localRemoteScript = Join-Path $PSScriptRoot 'windows\restart_catia_mcp_in_session.ps1'
if (-not (Test-Path -LiteralPath $localRemoteScript -PathType Leaf)) {
    throw "Local remote restart script does not exist: $localRemoteScript"
}

Write-Host "Checking WinRM on $ComputerName..."
Test-WSMan -ComputerName $ComputerName | Out-Null

$session = New-PSSession -ComputerName $ComputerName -Credential $credential
try {
    if (-not $SkipUpload) {
        Write-Host "Uploading remote restart script to $RemoteScriptPath..."
        Invoke-Command -Session $session -ArgumentList (Split-Path -Parent $RemoteScriptPath) -ScriptBlock {
            param($RemoteDirectory)
            New-Item -ItemType Directory -Force -Path $RemoteDirectory | Out-Null
        }
        Copy-Item -ToSession $session -Path $localRemoteScript -Destination $RemoteScriptPath -Force
    }

    if (-not $SkipTokenSync) {
        Write-Host "Syncing remote token file..."
        Invoke-Command -Session $session -ArgumentList $RemoteTokenFile, $deploy.MCP_TOKEN -ScriptBlock {
            param($TokenPath, $TokenValue)
            $directory = Split-Path -Parent $TokenPath
            New-Item -ItemType Directory -Force -Path $directory | Out-Null
            Set-Content -LiteralPath $TokenPath -Value "CATIA_MCP_TOKEN=$TokenValue" -Encoding ASCII
        }
    }

    Write-Host "Invoking remote restart script..."
    $restartResult = Invoke-Command -Session $session -ArgumentList @(
        $RemoteScriptPath,
        $PythonPath,
        $RemoteRepoPath,
        $BindHost,
        $Port,
        ($AllowedHost -join ';'),
        $RemoteTokenFile,
        $TargetUser,
        [bool]$DryRun
    ) -ScriptBlock {
        param(
            $ScriptPath,
            $PythonPath,
            $RepoPath,
            $BindHost,
            $Port,
            $AllowedHostValue,
            $TokenFile,
            $TargetUser,
            $DryRunRequested
        )

        $AllowedHost = if ([string]::IsNullOrWhiteSpace($AllowedHostValue)) {
            @()
        } else {
            $AllowedHostValue -split ';'
        }

        $arguments = @{
            PythonPath = $PythonPath
            RepoPath = $RepoPath
            BindHost = $BindHost
            Port = $Port
            AllowedHost = $AllowedHost
            TokenFile = $TokenFile
            TargetUser = $TargetUser
        }
        if ($DryRunRequested) {
            $arguments.DryRun = $true
        }

        $scriptContent = Get-Content -LiteralPath $ScriptPath -Raw
        $scriptBlock = [scriptblock]::Create($scriptContent)
        & $scriptBlock @arguments
    }

    $restartResult

    if ($DryRun) {
        Write-Host "Dry run complete; no process was stopped or started."
        return
    }

    $uri = "http://$BindHost`:$Port/mcp/"
    $deadline = (Get-Date).AddSeconds($TimeoutSeconds)
    $lastError = $null
    Write-Host "Polling MCP initialize at $uri..."
    while ((Get-Date) -lt $deadline) {
        try {
            $response = Invoke-McpInitializeProbe -Uri $uri -Token $deploy.MCP_TOKEN
            if ($response.StatusCode -in @(200, 202)) {
                [pscustomobject]@{
                    Status = 'ready'
                    Uri = $uri
                    HttpStatusCode = $response.StatusCode
                    RestartResult = $restartResult
                }
                return
            }
            $lastError = "Unexpected HTTP status $($response.StatusCode)"
        } catch {
            $lastError = $_.Exception.Message
        }

        Start-Sleep -Seconds 2
    }

    throw "MCP server did not pass initialize within $TimeoutSeconds seconds. Last error: $lastError"
} finally {
    if ($session) {
        Remove-PSSession $session
    }
}
