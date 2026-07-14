param(
    [string]$PythonPath = 'C:\Users\sup02\AppData\Local\Programs\Python\Python311\python.exe',
    [string]$RepoPath = 'C:\Users\sup02\catia-v5-mcp-server',
    [string]$BindHost = '192.168.5.42',
    [int]$Port = 8000,
    [string[]]$AllowedHost = @('192.168.5.42:8000'),
    [string]$TokenFile = 'C:\Users\sup02\catia-v5-mcp-server\.catia-mcp-env',
    [string]$TargetUser = 'sup02',
    [int]$StartupWaitSeconds = 8,
    [switch]$DryRun
)

$ErrorActionPreference = 'Stop'

function ConvertTo-PSLiteral {
    param([Parameter(Mandatory = $true)][AllowEmptyString()][string]$Value)
    return "'" + $Value.Replace("'", "''") + "'"
}

function Get-McpProcess {
    param([int]$McpPort)

    Get-CimInstance Win32_Process -Filter "name='python.exe'" |
        Where-Object {
            $cmd = $_.CommandLine
            $cmd -and
            $cmd -match '(^|\s)-m\s+catia_mcp(\s|$)' -and
            $cmd -match '(^|\s)--http(\s|$)' -and
            $cmd -match "(^|\s)--port\s+$McpPort(\s|$)"
        }
}

function Get-ProcessOwnerName {
    param([Parameter(Mandatory = $true)]$Process)

    try {
        $owner = Invoke-CimMethod -InputObject $Process -MethodName GetOwner
        if ($owner.ReturnValue -eq 0 -and $owner.User) {
            if ($owner.Domain) {
                return "$($owner.Domain)\$($owner.User)"
            }
            return $owner.User
        }
    } catch {
        return $null
    }

    return $null
}

function Get-ActiveSessionIdForUser {
    param([Parameter(Mandatory = $true)][string]$UserName)

    $shortName = ($UserName -split '\\')[-1]
    $lines = & quser 2>$null
    foreach ($line in $lines | Select-Object -Skip 1) {
        $clean = $line.TrimStart('>').Trim()
        if (-not $clean) {
            continue
        }

        $parts = $clean -replace '\s+', ' '
        $tokens = $parts.Split(' ')
        if ($tokens.Count -lt 3 -or $tokens[0] -ne $shortName) {
            continue
        }

        # Active RDP sessions include a SESSIONNAME column; disconnected console
        # lines often do not, so support both shapes.
        if ($tokens.Count -ge 4 -and $tokens[3] -eq 'Active') {
            return [int]$tokens[2]
        }
        if ($tokens[2] -eq 'Active') {
            return [int]$tokens[1]
        }
    }

    return $null
}

function Get-TokenSourceProcess {
    param(
        [Parameter(Mandatory = $true)][int]$SessionId,
        [Parameter(Mandatory = $true)][string]$UserName
    )

    $shortName = ($UserName -split '\\')[-1]
    $candidateNames = @('explorer.exe', 'powershell.exe', 'pwsh.exe')
    foreach ($name in $candidateNames) {
        $candidates = Get-CimInstance Win32_Process -Filter "SessionId=$SessionId and name='$name'" |
            Sort-Object ProcessId
        foreach ($candidate in $candidates) {
            $ownerName = Get-ProcessOwnerName -Process $candidate
            $ownerShortName = if ($ownerName) { ($ownerName -split '\\')[-1] } else { $null }
            if (-not $ownerShortName -or $ownerShortName -eq $shortName) {
                return $candidate
            }
        }
    }

    throw "No explorer.exe/powershell.exe token source found for user '$UserName' in session $SessionId."
}

function Add-NativeProcessType {
    if ('CatiaMcp.NativeProcess' -as [type]) {
        return
    }

    Add-Type -TypeDefinition @'
using System;
using System.ComponentModel;
using System.Runtime.InteropServices;
using System.Text;

namespace CatiaMcp {
    public static class NativeProcess {
        private const UInt32 PROCESS_QUERY_LIMITED_INFORMATION = 0x1000;
        private const UInt32 TOKEN_ASSIGN_PRIMARY = 0x0001;
        private const UInt32 TOKEN_DUPLICATE = 0x0002;
        private const UInt32 TOKEN_QUERY = 0x0008;
        private const UInt32 TOKEN_ADJUST_DEFAULT = 0x0080;
        private const UInt32 TOKEN_ADJUST_SESSIONID = 0x0100;
        private const UInt32 MAXIMUM_ALLOWED = 0x02000000;
        private const UInt32 CREATE_NEW_CONSOLE = 0x00000010;
        private const UInt32 LOGON_WITH_PROFILE = 0x00000001;

        private enum SECURITY_IMPERSONATION_LEVEL {
            SecurityAnonymous = 0,
            SecurityIdentification = 1,
            SecurityImpersonation = 2,
            SecurityDelegation = 3
        }

        private enum TOKEN_TYPE {
            TokenPrimary = 1,
            TokenImpersonation = 2
        }

        [StructLayout(LayoutKind.Sequential)]
        private struct SECURITY_ATTRIBUTES {
            public UInt32 nLength;
            public IntPtr lpSecurityDescriptor;
            public bool bInheritHandle;
        }

        [StructLayout(LayoutKind.Sequential, CharSet = CharSet.Unicode)]
        private struct STARTUPINFO {
            public UInt32 cb;
            public string lpReserved;
            public string lpDesktop;
            public string lpTitle;
            public UInt32 dwX;
            public UInt32 dwY;
            public UInt32 dwXSize;
            public UInt32 dwYSize;
            public UInt32 dwXCountChars;
            public UInt32 dwYCountChars;
            public UInt32 dwFillAttribute;
            public UInt32 dwFlags;
            public UInt16 wShowWindow;
            public UInt16 cbReserved2;
            public IntPtr lpReserved2;
            public IntPtr hStdInput;
            public IntPtr hStdOutput;
            public IntPtr hStdError;
        }

        [StructLayout(LayoutKind.Sequential)]
        private struct PROCESS_INFORMATION {
            public IntPtr hProcess;
            public IntPtr hThread;
            public UInt32 dwProcessId;
            public UInt32 dwThreadId;
        }

        [DllImport("kernel32.dll", SetLastError = true)]
        private static extern IntPtr OpenProcess(UInt32 dwDesiredAccess, bool bInheritHandle, UInt32 dwProcessId);

        [DllImport("advapi32.dll", SetLastError = true)]
        private static extern bool OpenProcessToken(IntPtr ProcessHandle, UInt32 DesiredAccess, out IntPtr TokenHandle);

        [DllImport("advapi32.dll", SetLastError = true)]
        private static extern bool DuplicateTokenEx(
            IntPtr hExistingToken,
            UInt32 dwDesiredAccess,
            ref SECURITY_ATTRIBUTES lpTokenAttributes,
            SECURITY_IMPERSONATION_LEVEL ImpersonationLevel,
            TOKEN_TYPE TokenType,
            out IntPtr phNewToken);

        [DllImport("advapi32.dll", SetLastError = true, CharSet = CharSet.Unicode)]
        private static extern bool CreateProcessAsUser(
            IntPtr hToken,
            string lpApplicationName,
            StringBuilder lpCommandLine,
            IntPtr lpProcessAttributes,
            IntPtr lpThreadAttributes,
            bool bInheritHandles,
            UInt32 dwCreationFlags,
            IntPtr lpEnvironment,
            string lpCurrentDirectory,
            ref STARTUPINFO lpStartupInfo,
            out PROCESS_INFORMATION lpProcessInformation);

        [DllImport("advapi32.dll", SetLastError = true, CharSet = CharSet.Unicode)]
        private static extern bool CreateProcessWithTokenW(
            IntPtr hToken,
            UInt32 dwLogonFlags,
            string lpApplicationName,
            StringBuilder lpCommandLine,
            UInt32 dwCreationFlags,
            IntPtr lpEnvironment,
            string lpCurrentDirectory,
            ref STARTUPINFO lpStartupInfo,
            out PROCESS_INFORMATION lpProcessInformation);

        [DllImport("kernel32.dll", SetLastError = true)]
        private static extern bool CloseHandle(IntPtr hObject);

        public static UInt32 StartFromProcessToken(
            UInt32 sourceProcessId,
            string applicationName,
            string commandLine,
            string currentDirectory) {
            IntPtr processHandle = IntPtr.Zero;
            IntPtr tokenHandle = IntPtr.Zero;
            IntPtr primaryToken = IntPtr.Zero;
            PROCESS_INFORMATION processInfo = new PROCESS_INFORMATION();

            try {
                processHandle = OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, false, sourceProcessId);
                if (processHandle == IntPtr.Zero) {
                    throw new Win32Exception(Marshal.GetLastWin32Error(), "OpenProcess failed");
                }

                UInt32 tokenAccess = TOKEN_ASSIGN_PRIMARY | TOKEN_DUPLICATE | TOKEN_QUERY |
                    TOKEN_ADJUST_DEFAULT | TOKEN_ADJUST_SESSIONID;
                if (!OpenProcessToken(processHandle, tokenAccess, out tokenHandle)) {
                    throw new Win32Exception(Marshal.GetLastWin32Error(), "OpenProcessToken failed");
                }

                SECURITY_ATTRIBUTES tokenAttributes = new SECURITY_ATTRIBUTES();
                tokenAttributes.nLength = (UInt32)Marshal.SizeOf(typeof(SECURITY_ATTRIBUTES));
                if (!DuplicateTokenEx(
                    tokenHandle,
                    MAXIMUM_ALLOWED,
                    ref tokenAttributes,
                    SECURITY_IMPERSONATION_LEVEL.SecurityImpersonation,
                    TOKEN_TYPE.TokenPrimary,
                    out primaryToken)) {
                    throw new Win32Exception(Marshal.GetLastWin32Error(), "DuplicateTokenEx failed");
                }

                STARTUPINFO startupInfo = new STARTUPINFO();
                startupInfo.cb = (UInt32)Marshal.SizeOf(typeof(STARTUPINFO));
                startupInfo.lpDesktop = @"winsta0\default";
                UInt32 creationFlags = CREATE_NEW_CONSOLE;

                bool created = CreateProcessAsUser(
                    primaryToken,
                    applicationName,
                    new StringBuilder(commandLine),
                    IntPtr.Zero,
                    IntPtr.Zero,
                    false,
                    creationFlags,
                    IntPtr.Zero,
                    currentDirectory,
                    ref startupInfo,
                    out processInfo);

                if (!created) {
                    int createProcessAsUserError = Marshal.GetLastWin32Error();
                    STARTUPINFO tokenStartupInfo = new STARTUPINFO();
                    tokenStartupInfo.cb = (UInt32)Marshal.SizeOf(typeof(STARTUPINFO));

                    created = CreateProcessWithTokenW(
                        primaryToken,
                        LOGON_WITH_PROFILE,
                        null,
                        new StringBuilder(commandLine),
                        0,
                        IntPtr.Zero,
                        currentDirectory,
                        ref tokenStartupInfo,
                        out processInfo);

                    if (!created) {
                        int createProcessWithProfileError = Marshal.GetLastWin32Error();
                        created = CreateProcessWithTokenW(
                            primaryToken,
                            0,
                            null,
                            new StringBuilder(commandLine),
                            0,
                            IntPtr.Zero,
                            currentDirectory,
                            ref tokenStartupInfo,
                            out processInfo);

                        if (!created) {
                            int createProcessWithoutProfileError = Marshal.GetLastWin32Error();
                            created = CreateProcessWithTokenW(
                                tokenHandle,
                                LOGON_WITH_PROFILE,
                                null,
                                new StringBuilder(commandLine),
                                0,
                                IntPtr.Zero,
                                currentDirectory,
                                ref tokenStartupInfo,
                                out processInfo);

                            if (!created) {
                                int originalTokenWithProfileError = Marshal.GetLastWin32Error();
                                created = CreateProcessWithTokenW(
                                    tokenHandle,
                                    0,
                                    null,
                                    new StringBuilder(commandLine),
                                    0,
                                    IntPtr.Zero,
                                    currentDirectory,
                                    ref tokenStartupInfo,
                                    out processInfo);

                                if (!created) {
                                    int originalTokenWithoutProfileError = Marshal.GetLastWin32Error();
                                    throw new Win32Exception(
                                        originalTokenWithoutProfileError,
                                        "CreateProcessAsUser failed with " + createProcessAsUserError +
                                        "; CreateProcessWithTokenW(primary, LOGON_WITH_PROFILE) failed with " +
                                        createProcessWithProfileError +
                                        "; CreateProcessWithTokenW(primary, 0) failed with " +
                                        createProcessWithoutProfileError +
                                        "; CreateProcessWithTokenW(original, LOGON_WITH_PROFILE) failed with " +
                                        originalTokenWithProfileError +
                                        "; CreateProcessWithTokenW(original, 0) failed");
                                }
                            }
                        }
                    }
                }

                return processInfo.dwProcessId;
            } finally {
                if (processInfo.hThread != IntPtr.Zero) CloseHandle(processInfo.hThread);
                if (processInfo.hProcess != IntPtr.Zero) CloseHandle(processInfo.hProcess);
                if (primaryToken != IntPtr.Zero) CloseHandle(primaryToken);
                if (tokenHandle != IntPtr.Zero) CloseHandle(tokenHandle);
                if (processHandle != IntPtr.Zero) CloseHandle(processHandle);
            }
        }
    }
}
'@
}

function Invoke-TemporaryServiceLaunch {
    param(
        [Parameter(Mandatory = $true)][int]$SourceProcessId,
        [Parameter(Mandatory = $true)][string]$ApplicationName,
        [Parameter(Mandatory = $true)][string]$CommandLine,
        [Parameter(Mandatory = $true)][string]$CurrentDirectory
    )

    $serviceName = 'CatiaMcpSessionLauncher'
    $workDirectory = Join-Path $env:ProgramData 'CatiaMcpRestart'
    New-Item -ItemType Directory -Force -Path $workDirectory | Out-Null

    $instanceId = [guid]::NewGuid().ToString('N')
    $exePath = Join-Path $workDirectory "CatiaMcpSessionLauncher-$instanceId.exe"
    $configPath = Join-Path $workDirectory "CatiaMcpSessionLauncher-$instanceId.txt"
    $resultPath = Join-Path $workDirectory "CatiaMcpSessionLauncher-$instanceId.result.txt"

    $commandLineB64 = [Convert]::ToBase64String([Text.Encoding]::Unicode.GetBytes($CommandLine))
    $configLines = @(
        "SourceProcessId=$SourceProcessId",
        "ApplicationName=$ApplicationName",
        "CommandLineB64=$commandLineB64",
        "CurrentDirectory=$CurrentDirectory",
        "ResultPath=$resultPath"
    )
    Set-Content -LiteralPath $configPath -Value $configLines -Encoding ASCII

    $serviceSource = @'
using System;
using System.Collections.Generic;
using System.ComponentModel;
using System.IO;
using System.Runtime.InteropServices;
using System.ServiceProcess;
using System.Text;
using System.Threading;

namespace CatiaMcp {
    public sealed class SessionLauncherService : ServiceBase {
        private static string[] processArgs = new string[0];

        public SessionLauncherService() {
            ServiceName = "CatiaMcpSessionLauncher";
            CanStop = true;
        }

        protected override void OnStart(string[] args) {
            string[] effectiveArgs = args.Length > 0 ? args : processArgs;
            ThreadPool.QueueUserWorkItem(_ => {
                try {
                    RunLauncher(effectiveArgs);
                } finally {
                    Stop();
                }
            });
        }

        public static void Main(string[] args) {
            if (args.Length > 0 && args[0] == "--console") {
                RunLauncher(new string[] { args[1] });
                return;
            }
            processArgs = args;
            ServiceBase.Run(new SessionLauncherService());
        }

        private static void RunLauncher(string[] args) {
            if (args.Length < 1) {
                throw new ArgumentException("Missing launcher config path.");
            }

            Dictionary<string, string> config = ReadConfig(args[0]);
            string resultPath = config["ResultPath"];
            try {
                UInt32 pid = NativeProcess.StartFromProcessToken(
                    UInt32.Parse(config["SourceProcessId"]),
                    config["ApplicationName"],
                    Encoding.Unicode.GetString(Convert.FromBase64String(config["CommandLineB64"])),
                    config["CurrentDirectory"]);
                File.WriteAllText(resultPath, "OK\nProcessId=" + pid + "\n");
            } catch (Exception ex) {
                File.WriteAllText(resultPath, "ERROR\n" + ex.ToString());
                throw;
            }
        }

        private static Dictionary<string, string> ReadConfig(string path) {
            Dictionary<string, string> values = new Dictionary<string, string>(StringComparer.OrdinalIgnoreCase);
            foreach (string line in File.ReadAllLines(path)) {
                int separator = line.IndexOf('=');
                if (separator > 0) {
                    values[line.Substring(0, separator)] = line.Substring(separator + 1);
                }
            }
            return values;
        }
    }

    public static class NativeProcess {
        private const UInt32 PROCESS_QUERY_LIMITED_INFORMATION = 0x1000;
        private const UInt32 TOKEN_ASSIGN_PRIMARY = 0x0001;
        private const UInt32 TOKEN_DUPLICATE = 0x0002;
        private const UInt32 TOKEN_QUERY = 0x0008;
        private const UInt32 TOKEN_ADJUST_DEFAULT = 0x0080;
        private const UInt32 TOKEN_ADJUST_SESSIONID = 0x0100;
        private const UInt32 MAXIMUM_ALLOWED = 0x02000000;
        private const UInt32 CREATE_NEW_CONSOLE = 0x00000010;

        private enum SECURITY_IMPERSONATION_LEVEL {
            SecurityAnonymous = 0,
            SecurityIdentification = 1,
            SecurityImpersonation = 2,
            SecurityDelegation = 3
        }

        private enum TOKEN_TYPE {
            TokenPrimary = 1,
            TokenImpersonation = 2
        }

        [StructLayout(LayoutKind.Sequential)]
        private struct SECURITY_ATTRIBUTES {
            public UInt32 nLength;
            public IntPtr lpSecurityDescriptor;
            public bool bInheritHandle;
        }

        [StructLayout(LayoutKind.Sequential, CharSet = CharSet.Unicode)]
        private struct STARTUPINFO {
            public UInt32 cb;
            public string lpReserved;
            public string lpDesktop;
            public string lpTitle;
            public UInt32 dwX;
            public UInt32 dwY;
            public UInt32 dwXSize;
            public UInt32 dwYSize;
            public UInt32 dwXCountChars;
            public UInt32 dwYCountChars;
            public UInt32 dwFillAttribute;
            public UInt32 dwFlags;
            public UInt16 wShowWindow;
            public UInt16 cbReserved2;
            public IntPtr lpReserved2;
            public IntPtr hStdInput;
            public IntPtr hStdOutput;
            public IntPtr hStdError;
        }

        [StructLayout(LayoutKind.Sequential)]
        private struct PROCESS_INFORMATION {
            public IntPtr hProcess;
            public IntPtr hThread;
            public UInt32 dwProcessId;
            public UInt32 dwThreadId;
        }

        [DllImport("kernel32.dll", SetLastError = true)]
        private static extern IntPtr OpenProcess(UInt32 dwDesiredAccess, bool bInheritHandle, UInt32 dwProcessId);

        [DllImport("advapi32.dll", SetLastError = true)]
        private static extern bool OpenProcessToken(IntPtr ProcessHandle, UInt32 DesiredAccess, out IntPtr TokenHandle);

        [DllImport("advapi32.dll", SetLastError = true)]
        private static extern bool DuplicateTokenEx(
            IntPtr hExistingToken,
            UInt32 dwDesiredAccess,
            ref SECURITY_ATTRIBUTES lpTokenAttributes,
            SECURITY_IMPERSONATION_LEVEL ImpersonationLevel,
            TOKEN_TYPE TokenType,
            out IntPtr phNewToken);

        [DllImport("advapi32.dll", SetLastError = true, CharSet = CharSet.Unicode)]
        private static extern bool CreateProcessAsUser(
            IntPtr hToken,
            string lpApplicationName,
            StringBuilder lpCommandLine,
            IntPtr lpProcessAttributes,
            IntPtr lpThreadAttributes,
            bool bInheritHandles,
            UInt32 dwCreationFlags,
            IntPtr lpEnvironment,
            string lpCurrentDirectory,
            ref STARTUPINFO lpStartupInfo,
            out PROCESS_INFORMATION lpProcessInformation);

        [DllImport("kernel32.dll", SetLastError = true)]
        private static extern bool CloseHandle(IntPtr hObject);

        public static UInt32 StartFromProcessToken(
            UInt32 sourceProcessId,
            string applicationName,
            string commandLine,
            string currentDirectory) {
            IntPtr processHandle = IntPtr.Zero;
            IntPtr tokenHandle = IntPtr.Zero;
            IntPtr primaryToken = IntPtr.Zero;
            PROCESS_INFORMATION processInfo = new PROCESS_INFORMATION();

            try {
                processHandle = OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, false, sourceProcessId);
                if (processHandle == IntPtr.Zero) {
                    throw new Win32Exception(Marshal.GetLastWin32Error(), "OpenProcess failed");
                }

                UInt32 tokenAccess = TOKEN_ASSIGN_PRIMARY | TOKEN_DUPLICATE | TOKEN_QUERY |
                    TOKEN_ADJUST_DEFAULT | TOKEN_ADJUST_SESSIONID;
                if (!OpenProcessToken(processHandle, tokenAccess, out tokenHandle)) {
                    throw new Win32Exception(Marshal.GetLastWin32Error(), "OpenProcessToken failed");
                }

                SECURITY_ATTRIBUTES tokenAttributes = new SECURITY_ATTRIBUTES();
                tokenAttributes.nLength = (UInt32)Marshal.SizeOf(typeof(SECURITY_ATTRIBUTES));
                if (!DuplicateTokenEx(
                    tokenHandle,
                    MAXIMUM_ALLOWED,
                    ref tokenAttributes,
                    SECURITY_IMPERSONATION_LEVEL.SecurityImpersonation,
                    TOKEN_TYPE.TokenPrimary,
                    out primaryToken)) {
                    throw new Win32Exception(Marshal.GetLastWin32Error(), "DuplicateTokenEx failed");
                }

                STARTUPINFO startupInfo = new STARTUPINFO();
                startupInfo.cb = (UInt32)Marshal.SizeOf(typeof(STARTUPINFO));
                startupInfo.lpDesktop = @"winsta0\default";

                if (!CreateProcessAsUser(
                    primaryToken,
                    applicationName,
                    new StringBuilder(commandLine),
                    IntPtr.Zero,
                    IntPtr.Zero,
                    false,
                    CREATE_NEW_CONSOLE,
                    IntPtr.Zero,
                    currentDirectory,
                    ref startupInfo,
                    out processInfo)) {
                    throw new Win32Exception(Marshal.GetLastWin32Error(), "CreateProcessAsUser failed");
                }

                return processInfo.dwProcessId;
            } finally {
                if (processInfo.hThread != IntPtr.Zero) CloseHandle(processInfo.hThread);
                if (processInfo.hProcess != IntPtr.Zero) CloseHandle(processInfo.hProcess);
                if (primaryToken != IntPtr.Zero) CloseHandle(primaryToken);
                if (tokenHandle != IntPtr.Zero) CloseHandle(tokenHandle);
                if (processHandle != IntPtr.Zero) CloseHandle(processHandle);
            }
        }
    }
}
'@

    Add-Type `
        -TypeDefinition $serviceSource `
        -Language CSharp `
        -ReferencedAssemblies 'System.ServiceProcess.dll' `
        -OutputAssembly $exePath `
        -OutputType WindowsApplication

    $existingService = Get-Service -Name $serviceName -ErrorAction SilentlyContinue
    if ($existingService) {
        & sc.exe delete $serviceName | Out-Null
        Start-Sleep -Seconds 1
    }

    $binaryPath = '"' + $exePath + '" "' + $configPath + '"'
    New-Service -Name $serviceName -BinaryPathName $binaryPath -StartupType Manual | Out-Null
    try {
        try {
            Start-Service -Name $serviceName -ErrorAction Stop
        } catch {
            # A one-shot launcher can complete before Service Control Manager is
            # satisfied. The result file below is the source of truth.
        }

        $deadline = (Get-Date).AddSeconds(30)
        while ((Get-Date) -lt $deadline -and -not (Test-Path -LiteralPath $resultPath)) {
            Start-Sleep -Milliseconds 500
        }

        if (-not (Test-Path -LiteralPath $resultPath)) {
            throw "Temporary service launcher did not write a result file."
        }

        $result = Get-Content -LiteralPath $resultPath
        if ($result[0] -ne 'OK') {
            throw "Temporary service launcher failed: $($result -join [Environment]::NewLine)"
        }

        $pidLine = $result | Where-Object { $_ -match '^ProcessId=(\d+)$' } | Select-Object -First 1
        if (-not $pidLine) {
            throw "Temporary service launcher did not report a process id."
        }

        if ($pidLine -notmatch '^ProcessId=(\d+)$') {
            throw "Temporary service launcher reported an invalid process id line: $pidLine"
        }
        return [uint32]$matches[1]
    } finally {
        $service = Get-Service -Name $serviceName -ErrorAction SilentlyContinue
        if ($service -and $service.Status -ne 'Stopped') {
            Stop-Service -Name $serviceName -Force -ErrorAction SilentlyContinue
        }
        & sc.exe delete $serviceName | Out-Null
        Get-CimInstance Win32_Process -Filter "name='$(Split-Path -Leaf $exePath)'" -ErrorAction SilentlyContinue |
            Where-Object { $_.CommandLine -like "*$exePath*" } |
            ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }
        Remove-Item -LiteralPath $exePath, $configPath, $resultPath -Force -ErrorAction SilentlyContinue
    }
}

if (-not (Test-Path -LiteralPath $PythonPath -PathType Leaf)) {
    throw "PythonPath does not exist: $PythonPath"
}
if (-not (Test-Path -LiteralPath $RepoPath -PathType Container)) {
    throw "RepoPath does not exist: $RepoPath"
}
if (-not (Test-Path -LiteralPath $TokenFile -PathType Leaf)) {
    throw "TokenFile does not exist: $TokenFile"
}

$mcpProcesses = @(Get-McpProcess -McpPort $Port)
$targetSessionId = $null
if ($mcpProcesses.Count -gt 0) {
    $targetSessionId = [int]($mcpProcesses | Sort-Object ProcessId | Select-Object -First 1).SessionId
}
if ($null -eq $targetSessionId) {
    $targetSessionId = Get-ActiveSessionIdForUser -UserName $TargetUser
}
if ($null -eq $targetSessionId) {
    throw "Could not determine an active interactive session for '$TargetUser'."
}

$tokenSource = Get-TokenSourceProcess -SessionId $targetSessionId -UserName $TargetUser

$serverArgs = @(
    '-m',
    'catia_mcp',
    '--http',
    '--host',
    $BindHost,
    '--port',
    [string]$Port
)
foreach ($hostName in $AllowedHost) {
    $serverArgs += @('--allowed-host', $hostName)
}

$serverArgsLiteral = ($serverArgs | ForEach-Object { ConvertTo-PSLiteral $_ }) -join ', '
$launchScript = @"
`$ErrorActionPreference = 'Stop'
`$token = ''
foreach (`$line in Get-Content -LiteralPath $(ConvertTo-PSLiteral $TokenFile)) {
    if (`$line -match '^\s*(?:CATIA_MCP_TOKEN|MCP_TOKEN)\s*[:=]\s*(.+)\s*$') {
        `$token = `$matches[1].Trim()
        break
    }
}
if (-not `$token) {
    throw 'CATIA_MCP_TOKEN or MCP_TOKEN was not found in the token file.'
}
`$env:CATIA_MCP_TOKEN = `$token
Set-Location -LiteralPath $(ConvertTo-PSLiteral $RepoPath)
`$serverArgs = @($serverArgsLiteral)
& $(ConvertTo-PSLiteral $PythonPath) @serverArgs
"@

$powerShellPath = Join-Path $env:SystemRoot 'System32\WindowsPowerShell\v1.0\powershell.exe'
$encodedLaunch = [Convert]::ToBase64String([Text.Encoding]::Unicode.GetBytes($launchScript))
$commandLine = '"' + $powerShellPath + '" -NoProfile -ExecutionPolicy Bypass -EncodedCommand ' + $encodedLaunch

Add-NativeProcessType

if ($DryRun) {
    [pscustomobject]@{
        DryRun = $true
        TargetSessionId = $targetSessionId
        TokenSourceProcessId = $tokenSource.ProcessId
        TokenSourceName = $tokenSource.Name
        ExistingMcpProcessIds = @($mcpProcesses | ForEach-Object { $_.ProcessId })
        LaunchApplication = $powerShellPath
        LaunchWorkingDirectory = $RepoPath
        ServerArgs = $serverArgs
    }
    return
}

foreach ($process in $mcpProcesses) {
    Stop-Process -Id $process.ProcessId -Force -ErrorAction Stop
}

$deadline = (Get-Date).AddSeconds(10)
while ((Get-Date) -lt $deadline) {
    $remaining = @(Get-McpProcess -McpPort $Port)
    if ($remaining.Count -eq 0) {
        break
    }
    Start-Sleep -Milliseconds 250
}

$launchMethod = 'direct-token'
$directLaunchError = $null
try {
    $launcherPid = [CatiaMcp.NativeProcess]::StartFromProcessToken(
        [uint32]$tokenSource.ProcessId,
        $powerShellPath,
        $commandLine,
        $RepoPath)
} catch {
    $directLaunchError = $_.Exception.Message
    $launchMethod = 'temporary-service'
    $launcherPid = Invoke-TemporaryServiceLaunch `
        -SourceProcessId $tokenSource.ProcessId `
        -ApplicationName $powerShellPath `
        -CommandLine $commandLine `
        -CurrentDirectory $RepoPath
}

$newMcpProcess = $null
$deadline = (Get-Date).AddSeconds($StartupWaitSeconds)
while ((Get-Date) -lt $deadline) {
    $newMcpProcess = @(Get-McpProcess -McpPort $Port |
        Where-Object { $_.SessionId -eq $targetSessionId } |
        Sort-Object ProcessId |
        Select-Object -Last 1)
    if ($newMcpProcess.Count -gt 0) {
        break
    }
    Start-Sleep -Milliseconds 500
}

[pscustomobject]@{
    DryRun = $false
    TargetSessionId = $targetSessionId
    TokenSourceProcessId = $tokenSource.ProcessId
    TokenSourceName = $tokenSource.Name
    LaunchMethod = $launchMethod
    DirectLaunchError = $directLaunchError
    StoppedMcpProcessIds = @($mcpProcesses | ForEach-Object { $_.ProcessId })
    LauncherProcessId = $launcherPid
    NewMcpProcessIds = @($newMcpProcess | ForEach-Object { $_.ProcessId })
    NewMcpSessionIds = @($newMcpProcess | ForEach-Object { $_.SessionId })
}
