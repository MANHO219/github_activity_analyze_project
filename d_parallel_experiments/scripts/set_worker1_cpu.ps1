param([Parameter(Mandatory=$true)][ValidateSet(1,4)][int]$Cores)
$ErrorActionPreference = 'Stop'
$taskVmrun = 'E:\VMware\vmrun.exe'
$taskVmx = 'E:\VMEntity\Ubuntu\Ubuntu26.04.vmx'
$taskRunning = & $taskVmrun list
if ($LASTEXITCODE -ne 0) { throw 'Cannot inspect running VMs' }
if ($taskRunning -contains $taskVmx) { throw 'Worker 1 must be fully powered off before changing CPU' }
$taskConfig = [System.IO.File]::ReadAllText($taskVmx)
if ($taskConfig -notmatch 'displayName = "spark-worker-1"') { throw 'Unexpected VM identity' }
if (([regex]::Matches($taskConfig,'(?m)^numvcpus = ')).Count -ne 1) { throw 'Unexpected CPU setting' }
if (([regex]::Matches($taskConfig,'(?m)^cpuid.coresPerSocket = ')).Count -ne 1) { throw 'Unexpected socket setting' }
$taskBackup = $taskVmx + '.before-cpu-' + (Get-Date -Format 'yyyyMMdd-HHmmss')
Copy-Item -LiteralPath $taskVmx -Destination $taskBackup
$taskConfig = [regex]::Replace($taskConfig,'(?m)^numvcpus = "\d+"',('numvcpus = "'+$Cores+'"'))
$taskConfig = [regex]::Replace($taskConfig,'(?m)^cpuid.coresPerSocket = "\d+"',('cpuid.coresPerSocket = "'+$Cores+'"'))
[System.IO.File]::WriteAllText($taskVmx,$taskConfig,[System.Text.UTF8Encoding]::new($false))
Write-Output "Worker 1 configured for $Cores vCPU; backup: $taskBackup"
