<#
	.SYNOPSIS
		Sumologic Agent Installer for Windows Hosts or construct a cmd line.
        
        .DESCRIPTION
		* Downloads and installs latest version of the Sumologic Agent:
        https://help.sumologic.com/03Send-Data/Installed-Collectors/03Install-a-Collector-on-Windows
        * runs install or outputs command line

        Use flags to control behaviour - default is dsi
        d - download
        s - create sources
        i - install
        u - upgrade

    .PARAMETER SUMO_COLLECTOR_NAME		
        Optional: SUMO_COLLECTOR_NAME optional name string to override the collector name. 
		Note restrictions on valid characters only alphanumeric and very limited punctuation are allowed.

    .PARAMETER SumoBinary
        Optional: Full path to the installer exe any http path such as s3 or sumo.
        default:
        -SumoBinary = "https://collectors.au.sumologic.com/rest/download/win64" 

    .PARAMETER DownloadVersion
        Optional, defaults to latest. 
        Specify an agent version eg. 19.288-3
        This will be appended as a version=<version> query paramenter for the sumo downloader url.
        Will only work with default sumo download url

    .PARAMETER localBinary
        Optional: Path to local downloaded file (or about to be downloaded binary).
        If this exists download would be skipped.

    .PARAMETER installPath
        Optional: As one would expect where it will be installed

    .PARAMETER SUMO_ACCESS_ID        
        default $env:SUMO_ACCESS_ID 
        can be set later in user.properties if you are using vSkipRegistration

    .PARAMETER SUMO_ACCESS_KEY        
        default: $env:SUMO_ACCESS_KEY 
        can be set later in user.properties if you are using vSkipRegistration

    .PARAMETER proxyHost
        Optional: proxyHost optional string to add a proxy to user.properties  -Vproxy.host=[host] 

    .PARAMETER proxyPort
        Optional: proxyPort optional string to specify a port to user.properties -Vproxy.port=[port] 

    .PARAMETER SyncSourcesPath
        Optional: SyncSourcesPath optional string to specify syncsources path path. -VsyncSources=[filepath] 

    .PARAMETER VskipRegistration
        Optional Switch:  switch -VskipRegistration enables -VskipRegistration=true
		Use of this feature is for packaging in images such as AMI etc.
        Typicalyl one would have an instance launch script that configures user.properties and launches sumo. 
        If set service is set to manual start which you must undo later at instance launch.
 
    .PARAMETER source_library
        either 
        - 'DEFAULT' - reads from 'here string' in this script or 
        - a path to the library sources file e.g: "./source_library.json" in the 'multiple sources' format.
        This file will be filtered based on the source_include and exclude params, and written to sourcespath/*.json
        Where * is the source name with non alpha-numeric chrs replaced with _.
        Tokenise the library file by using {{SUMO_VAR}} format and any SUMO_VAR env var will be replaced with env value.

    .PARAMETER source_include
        a regular expression of source names to include from the library file
        defaults to:  ".*"
        
    .PARAMETER source_exclude
        a regular expression of source names to exclude from the library file
        default: "NOTHING"

    .PARAMETER flags
        flag string:
        d - download
        s - create sources
        i - install
        u - upgrade

	.PARAMETER SUMO_EPHEMERAL
		switch set to true to make host ephemeral-ness  
        default behaviour is 'ephemeral=true' which means host will DELETE itself from sumo if no data for 12 hours. 
        
    .EXAMPLE
    .\sumologic-windows-install-basic.ps1 -VskipRegistration
    install agent only with minimal config and manual service start for use in images such as AMI

    .EXAMPLE
    .\sumologic-windows-install-basic.ps1-SUMO_ACCESS_ID XXXX -SUMO_ACCESS_KEY YYYY  -SUMO_COLLECTOR_NAME "custom_name" -SyncSourcesPath "c:\sumojson"
    Typical install with defaults and local file config in "c:\sumo.json.files\"
    
    .EXAMPLE
    .\sumologic-windows-install-basic.ps1 -flags 'du' 
    upgrade an agent to latest version in place

            
    .EXAMPLE
    .\sumologic-windows-install-basic.ps1 -flags 's' -$ource_library 'c:\myfile\some.json'
    configure sources only using templated sources

<# ==========================================================
       Configuration Section Start
===========================================================#>
param (
    [Parameter(Mandatory = $false)][string] $SUMO_COLLECTOR_NAME, # -Vcollector.name=[name]
    [Parameter(Mandatory = $false)][string] $SumoBinary = 'https://collectors.au.sumologic.com/rest/download/win64', # defaults to latest
    [Parameter(Mandatory = $false)][string] $localBinary = "c:\temp\sumologic.exe",
    [Parameter(Mandatory = $false)][string] $downloadVersion = "latest",
    [Parameter(Mandatory = $false)][string] $install_path = "C:\Sumo\SumoLogicCollector",
    [Parameter(Mandatory = $false)][string] $SUMO_ACCESS_ID = $env:SUMO_ACCESS_ID,
    [Parameter(Mandatory = $false)][string] $SUMO_ACCESS_KEY = $env:SUMO_ACCESS_KEY,
    [Parameter(Mandatory = $false)][string] $proxyHost, 
    [Parameter(Mandatory = $false)][string] $proxyPort, 
    [Parameter(Mandatory = $false)][string] $SyncSourcesPath = "c:\sumojson\", 
    [Parameter(Mandatory = $false)][string] $SourcesPath ,
    [Parameter(Mandatory = $false)][bool] $SUMO_EPHEMERAL = $true,
    [Parameter(Mandatory = $false)][string] $source_library = 'DEFAULT', #"./source_library.json",
    [Parameter(Mandatory = $false)][string] $source_include = ".*",
    [Parameter(Mandatory = $false)][string] $source_exclude = "NOTHING",
    [Parameter(Mandatory = $false)][string] $flags = "dsi",
    [switch]  $VskipRegistration
)

# Logging config
$timestamp = [string]$("{0:yyyy_MM_dd_hh.mm.ss}" -f (Get-Date))
write-host "Script started at: $timestamp"

function defaultSources {
    $json = @'
    {
        "api.version": "v1",
        "sources": [
            {
                "name": "os_windows",
                "description": "windows event logs new json format",
                "category": "os/windows/events",
                "automaticDateParsing": true,
                "multilineProcessingEnabled": false,
                "useAutolineMatching": false,
                "forceTimeZone": false,
                "filters": [],
                "cutoffRelativeTime": "-1h",
                "allowlist":"",
                "renderMessages":false,
                "logNames":["Application","System","Security"],
                "denylist":"",
                "eventFormat":1,
                "eventMessage":0,
                "sidStyle":2,
                "sourceType":"LocalWindowsEventLog"
            },
            {
                "name":"HostMetrics",
                "description":"HostMetrics",
                "category":"hostmetrics",
                "automaticDateParsing":false,
                "multilineProcessingEnabled":false,
                "useAutolineMatching":false,
                "contentType":"HostMetrics",
                "forceTimeZone":false,
                "filters":[],
                "cutoffTimestamp":0,
                "encoding":"UTF-8",
                "fields":{
                  
                },
                "interval":60000,
                "metrics":["CPU_User","CPU_Sys","CPU_Nice","CPU_Idle","CPU_IOWait","CPU_Irq","CPU_SoftIrq","CPU_Stolen","CPU_LoadAvg_1min","CPU_LoadAvg_5min","CPU_LoadAvg_15min","CPU_Total","Mem_Total","Mem_Used","Mem_Free","Mem_ActualFree","Mem_ActualUsed","Mem_UsedPercent","Mem_FreePercent","Mem_PhysicalRam","Disk_Used","Disk_UsedPercent","Disk_Available"],
                "sourceType":"SystemStats"
              }
        ]
    }
'@
    return $json | ConvertFrom-Json #-Depth 20
}
function Read-SourceLibrary {
    param (
        [Parameter(Mandatory = $false)][string] $sources_library_path = "./source_library.json",
        [Parameter(Mandatory = $false)][string] $return = "sources" # or object

    )
    if ($sources_library_path -eq 'DEFAULT' ) {
        $sources = defaultSources
    }
    else {

        if (Test-Path -Path $sources_library_path) {
            $sourceLib = get-Content -Path "$sources_library_path" -raw | ConvertFrom-Json #-Depth 20
            if ($sourceLib.sources) { 
        
            }
            else {
                Write-Error "failed to read valid sources file: $sources_library_path No sources key."
                break
            }
            if ($return -eq "sources" ) {
                $sources = $sourceLib.sources
                Write-Verbose "got: $($sources.count) sources in library file: $sources_library_path"
            }
            else {
                $sources = $sourceLib
            }
        }
        else {
            Write-Error "Sources library path not found: $sources_library_path"
        }
    }
            
    return $sources


}

function Select-SourceLibrary {
    param (
        [Parameter(Mandatory = $true)] $sources, 
        [Parameter(Mandatory = $false)][string] $include_sources = ".*", 
        [Parameter(Mandatory = $false)][string] $exclude_sources = "EXCLUDE NOTHING"
    )
    $filteredSources = @()
    foreach ($source in $sources) {
        Write-Verbose "source: $($source.name)"
        if ($source.name -match $include_sources -and $source.name -notmatch $exclude_sources) {
            Write-Host "Include source: $($source.name) from library file."
            $filteredSources = $filteredSources + $source
        }
    }
    return [array]$filteredSources
}

# Write each source in the array to a separate json file
function write-sourceFiles { 
    param (
        [Parameter(Mandatory = $true)] $sources, 
        [Parameter(Mandatory = $true)][string] $sourcesFilePath
    )

    foreach ($source in $sources) {
        $stub = @{
            "api.version" = "v1";
            "source"      = $source
        }

        $name = $source.name -replace "[^a-z0-9_-]", "_"
        $filepath = "$sourcesFilePath\$($name).json"

        write-host "Creating $filepath"
        $stub | convertto-json  | out-file -FilePath "$filepath" -Encoding ascii

    }

}
function Set-SourceVariables {
    param (
        [Parameter(Mandatory = $true)] $source,
        [Parameter(Mandatory = $false)] $properties = @("name", "description", "category")
    )

    # get any sumo env vars
    $sumo_env = dir env: | where { $_.name -match 'SUMO' }
    
    Write-Verbose "checking source: $($source_copy.name)"
    # replace any [SUMO_VAR] in properties
    foreach ($property in $properties) {
        Write-Verbose "checking property: $property"
        foreach ($var in $sumo_env) {
            $n = $var.name 
            $v = $var.value

            if ($source.$property -match $var.name) {
                Write-Verbose "$n = $v"
                Write-Verbose $source.$property
                $source.$property = ($source.$property.tostring()).replace("{{$n}}", "$v")
            }
        }
    }
    return $source
}

function Set-Arguments {

    if ($install_path) {
        new-item -Path "$install_path" -ItemType Directory -force -ErrorAction SilentlyContinue  | Out-Null
        if (!(Test-Path $install_path)) {
            throw "Path to the Installation Directory $($install_path) is invalid. Please supply a valid installation directory"
            exit
        }
    }
    
    $arguments = @(
        "-q"
        "-dir $install_path"
        "`"-Vsumo.accessid=$SUMO_ACCESS_ID`""
        "`"-Vsumo.accesskey=$SUMO_ACCESS_KEY`""
    )

    #[switch]  $VskipRegistration,   # -VskipRegistration=true
    if ($VskipRegistration) { $arguments += "`"-VskipRegistration=true`"" }

    # The command line installer can use all of the parameters available in the user.properties file. 
    # To use parameters from user.properties just add a -V to the beginning of the parameter without a space character. 
    # For example, to use the sources parameter you would specify it as -Vsources.
    if ($SUMO_EPHEMERAL) { $arguments += "`"-Vephemeral=true`"" } else { $arguments += "`"-Vephemeral=false`"" }
    if ($proxyHost) { $arguments += "`"-Vproxy.host=$proxyHost`"" }
    if ($proxyPort) { $arguments += "`"-Vproxy.port=$proxyPort`"" }

    # setup collector name if custom
    if ($SUMO_COLLECTOR_NAME) {  
        if ($SUMO_COLLECTOR_NAME.Length -gt 127) { $SUMO_COLLECTOR_NAME = $SUMO_COLLECTOR_NAME.Substring(0, 126) }
        $arguments += "`"-Vcollector.name=$SUMO_COLLECTOR_NAME`"" 
    }

    # support various env variables
    IF ($ENV:SUMO_RECEIVER_URL) { $ARGUMENTS += "`"-url=$($ENV:SUMO_RECEIVER_URL)`"" } 
    #IF ($ENV:SUMO_PROXY_HOST) {  $ARGUMENTS += "`"-VproxyHost=$($ENV:SUMO_PROXY_HOST)`""} 
    #IF ($ENV:SUMO_PROXY_PORT) {  $ARGUMENTS += "`"-VproxyPort=$($ENV:SUMO_PROXY_PORT)`""} 
    IF ($ENV:SUMO_PROXY_USER) { $ARGUMENTS += "`"-VproxyUser=$($ENV:SUMO_PROXY_USER)`"" } 
    IF ($ENV:SUMO_PROXY_PASSWORD) { $ARGUMENTS += "`"-VproxyPassword=$($ENV:SUMO_PROXY_PASSWORD)`"" } 
    IF ($ENV:SUMO_PROXY_NTLM_DOMAIN) { $ARGUMENTS += "`"-VproxyNtlmDomain=$($ENV:SUMO_RECEIVER_URL)`"" } 
    IF ($ENV:SUMO_CLOBBER) { $ARGUMENTS += "`"-Vclobber=$($ENV:SUMO_CLOBBER)`"" } 
    #IF ($ENV:SUMO_DISABLE_SCRIPTS) {  $ARGUMENTS += "`"-VdisableScriptSource=$($ENV:SUMO_DISABLE_SCRIPTS)`""} 
    IF ($ENV:SUMO_JAVA_MEMORY_INIT) { $ARGUMENTS += "`"-Vwrapper.java.initmemory=$($ENV:SUMO_JAVA_MEMORY_INIT)`"" } 
    IF ($ENV:SUMO_JAVA_MEMORY_MAX) { $ARGUMENTS += "`"-Vwrapper.java.maxmemory=$($ENV:SUMO_JAVA_MEMORY_MAX)`"" } 
    #IF ($ENV:SUMO_EPHEMERAL) {  $ARGUMENTS += "`"-Vephemeral=$($ENV:SUMO_EPHEMERAL)`""} 
    IF ($ENV:SUMO_FIELDS) { $ARGUMENTS += "`"-Vfields=$($ENV:SUMO_FIELDS)`"" } 

    return $arguments
}

$commandArguments = Set-Arguments


if ($flags -match 's') {
    #### SOURCE CONFIGURATION
    # get the master file of all sources
    $SourcesMasterList = Read-SourceLibrary -sources_library_path $source_library -return 'object'
    $SourcesMasterList.sources = Select-SourceLibrary -sources $SourcesMasterList.sources -include_sources $source_include -exclude_sources $source_exclude
    $SourcesMasterList.sources = $SourcesMasterList.sources | foreach { Set-SourceVariables -source $_ }

    #  Make sure syncsourcespath dir exists or sources if that was used.
    if ($SyncSourcesPath) { 
        $sourcesFilePath = "$SyncSourcesPath"
        $commandArguments += "`"-VsyncSources=$sourcesFilePath`""
    }
    else {
        $sourcesFilePath = "$SourcesPath"
        $commandArguments += "`"-Vsources=$sourcesFilePath`""
    }
    $sourcesFilePath = $sourcesFilePath.Replace("\\", "\") 
    New-Item -ItemType directory -Path $SyncSourcesPath -force   | Out-Null
    write-sourceFiles -sources $SourcesMasterList.sources  -sourcesFilePath $sourcesFilePath

    Write-Verbose "sources config would be: $sourcesFilePath. `n($SourcesMasterList | convertto-json  )" 
} 


######################### EXECUTE OR OUTPUT THE COMMAND ##############################
if ($flags -match 'd') {  
    write-host "downloading: $downloadVersion"
    $p = split-path -Path "$localBinary"
    New-Item -Path $p -ItemType Directory -force -ErrorAction SilentlyContinue | Out-Null
    
    if ($downloadVersion -eq 'latest') {
        $Parameters = @{}
    }
    else {
        $localBinary = "$($localbinary | split-path)_$($downloadVersion)_$($localbinary | split-path -leaf)"
        $Parameters = @{
            version = $downloadVersion
        }
    }
    write-host "downloading: $SumoBinary to $localBinary"
    $Result = Invoke-WebRequest -Uri $SumoBinary -OutFile "$localBinary" -Body $Parameters -Method Get
}

if ($flags -match 'i' ) {
    Write-Host "executing: command: $localBinary $($commandArguments | where {$_ -notmatch 'key'}) "
    $process = Start-Process -FilePath $localBinary -ArgumentList $commandArguments -Wait -PassThru
    if ($process.ExitCode -eq 0) {
        Write-Verbose "$localBinary has been successfully installed"
    }
    else {
        Write-Error "installer exit code  $($process.ExitCode) for file  $($exefile)"
    }
}

if ($flags -match 'u' ) {
    Write-Host "executing: command: $localBinary -console -q "
    $process = Start-Process -FilePath $localBinary -ArgumentList  "-console -q" -Wait -PassThru
    if ($process.ExitCode -eq 0) {
        Write-Verbose "$localBinary has been upgraded"
    }
    else {
        Write-Error "installer exit code  $($process.ExitCode) for file  $($exefile)"
    }
}
if ($removeInstallFile) { if (Test-Path $file) { Remove-Item $file }	}		

if ($VskipRegistration -and $flags -match 'i') { 
    # prevent service starting on boot 
    # YOU MUST REVERT THIS IN YOUR STARTUP SCRIPT!!!
    Set-Service -Name sumo-collector -StartupType Manual
}

