param(
    [Parameter(Mandatory = $false)]
    [ValidateSet("run", "company", "tender", "regid", "resume", "smoke-test")]
    [string]$Command = "run",

    [Parameter(Mandatory = $false)]
    [string]$CompanyId,

    [Parameter(Mandatory = $false)]
    [string]$CompanyName,

    [Parameter(Mandatory = $false)]
    [string]$AppId,

    [Parameter(Mandatory = $false)]
    [string]$RegId,

    [Parameter(Mandatory = $false)]
    [string]$RunId,

    [switch]$DebugHtml
)

$argsList = @("-m", "tender_tracker", $Command)

if ($CompanyId) { $argsList += @("--company-id", $CompanyId) }
if ($CompanyName) { $argsList += @("--company-name", $CompanyName) }
if ($AppId) { $argsList += @("--app-id", $AppId) }
if ($RegId) { $argsList += @("--reg-id", $RegId) }
if ($RunId) { $argsList += @("--run-id", $RunId) }
if ($DebugHtml) { $argsList += "--debug" }

py @argsList
