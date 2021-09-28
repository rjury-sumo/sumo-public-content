<#
	.SYNOPSIS
		Sumologic Agent Installer for Windows Hosts or construct a cmd line.
        
        .DESCRIPTION
		* Downloads and installs latest version of the Sumologic Agent:
        https://help.sumologic.com/03Send-Data/Installed-Collectors/03Install-a-Collector-on-Windows
        * runs install or outputs command line

    .PARAMETER SUMO_COLLECTOR_NAME		
        Optional: SUMO_COLLECTOR_NAME optional name string to override the collector name. 
		Note restrictions on valid characters only alphanumeric and very limited punctuation are allowed.

    .PARAMETER SumoBinary
        Optional: Full path to the installer exe in an S3 bucket that your account can access.
             Example:
        -SumoBinary = "https://s3-ap-southeast-2.amazonaws.com/acme-binaries/installers/SumoCollector_windows-x64_19_137-20.exe" 

    .PARAMETER localBinary
        Optional: Path to local downloaded file (or about to be downloaded binary).
        If this exists download would be skipped.

    .PARAMETER installPath
        Optional: As one would expect where it will be installed

    .PARAMETER SUMO_ACCESS_ID        
        Mandatory: SUMO_ACCESS_ID 
        This could be stored in a system that calls this script and passed as a parameter.

    .PARAMETER SUMO_ACCESS_KEY        
        Mandatory: SUMO_ACCESS_KEY 
        This could be stored in a system that calls this script and passed as a parameter.

    .PARAMETER proxyHost
        Optional: proxyHost optional string to add a proxy to user.properties  -Vproxy.host=[host] 

    .PARAMETER proxyPort
        Optional: proxyPort optional string to specify a port to user.properties -Vproxy.port=[port] 

    .PARAMETER SyncSourcesPath
        Optional: SyncSourcesPath optional string to specify syncsources path path. -VsyncSources=[filepath] 
        Will be created if set.

    .PARAMETER VskipRegistration
        Optional Switch:  switch -VskipRegistration enables -VskipRegistration=true
		Use of this feature is for packaging in images such as AMI etc. 
 
    .PARAMETER source_library
        path to the library sources file default: "./source_library.json"
        This file will be filtered and written to sourcespath/sumo.json
        Tokenise the library file by using {{SUMO_VAR}} format.
        Any matching tokens to runtime env variables will be replaced in the final output file.

    .PARAMETER source_include
        a regular expression of source names to include from the library file
        defaults to:  "metrics"
        
    .PARAMETER source_exclude
        a regular expression of source names to exclude from the library file
        default: "NOTHING"

    .PARAMETER Dryrun
		output exec and args only, don't donwload or execute

	.PARAMETER SUMO_EPHEMERAL
		switch set to true to make host ephemeral-ness  
        default behaviour is 'ephemeral' which means host will DELETE itself from sumo if no data for 12 hours. 
        
    .EXAMPLE
        install agent only with minimal config and manual service start for use in images such as AMI
		.\sumologic-windows-agent-install.ps1 -VskipRegistration

    .EXAMPLE 
        output command only with -dryrun
         .\install-sumo.ps1 -VskipRegistration -Dryrun
        Script started at: 2021_05_21_03.09.38
        Output command only:
        Install command: c:\temp\sumologic.exe -q -dir C:\Sumo\SumoLogicCollector "-Vsumo.accessid=SET_ID" "-Vsumo.accesskey=SET_KEY" "-VskipRegistration=true" "-Vephemeral=false" 

    .EXAMPLE
        Typical install with defaults and local file config in "c:\sumo.json.files\"
		.\sumologic-windows-agent-install.ps1 -SUMO_ACCESS_ID XXXX -SUMO_ACCESS_KEY YYYY  -SUMO_COLLECTOR_NAME "custom_name" -SyncSourcesPath "c:\sumo.json.files\"

    
	.LINK
        https://github.com/acme/some-repo/#>

<# ==========================================================
       Configuration Section Start
===========================================================#>
param (
    [Parameter(Mandatory = $false)][string] $SUMO_COLLECTOR_NAME, # -Vcollector.name=[name]
    [Parameter(Mandatory = $false)][string] $SumoBinary = 'https://collectors.au.sumologic.com/rest/download/win64', # defaults to latest
    [Parameter(Mandatory = $false)][string] $localBinary = "c:\temp\sumologic.exe",
    [Parameter(Mandatory = $false)][string] $install_path = "C:\Sumo\SumoLogicCollector",
    [Parameter(Mandatory = $false)][string] $SUMO_ACCESS_ID = "SET_ID",
    [Parameter(Mandatory = $false)][string] $SUMO_ACCESS_KEY = "SET_KEY",
    [Parameter(Mandatory = $false)][string] $proxyHost, 
    [Parameter(Mandatory = $false)][string] $proxyPort, 
    [Parameter(Mandatory = $false)][string] $SyncSourcesPath, 
    [Parameter(Mandatory = $false)][string] $SourcesPath = "c:\sumo.json.files", 
    [Parameter(Mandatory = $false)][bool] $SUMO_EPHEMERAL = $true,
    [Parameter(Mandatory = $false)][string] $source_library = "./source_library.json",
    [Parameter(Mandatory = $false)][string] $source_include = "metrics",
    [Parameter(Mandatory = $false)][string] $source_exclude = "NOTHING",

    [switch]  $VskipRegistration, # -VskipRegistration=true
    [switch]  $Dryrun 
)

# Logging config
$timestamp = [string]$("{0:yyyy_MM_dd_hh.mm.ss}" -f (Get-Date))
write-host "Script started at: $timestamp"

function Read-SourceLibrary {
    param (
        [Parameter(Mandatory = $false)][string] $sources_library_path = "./source_library.json",
        [Parameter(Mandatory = $false)][string] $return = "sources" # or object

    )
        if (Test-Path -Path $sources_library_path) {
            $sourceLib = get-Content -Path "$sources_library_path" -raw | ConvertFrom-Json -Depth 20
            if ($sourceLib.sources) { 
    
            } else {
                Write-Error "failed to read valid sources file: $sources_library_path No sources key."
                break
            }
            if ($return -eq "sources" ) {
                $sources = $sourceLib.sources
                Write-Verbose "got: $($sources.count) sources in library file: $sources_library_path"
                return $sources
            } else {
                return $sourceLib
            }

        } else {
            Write-Error "Sources library path not found: $sources_library_path"
        }

}

function Select-SourceLibrary {
    param (
    [Parameter(Mandatory = $true)] $sources, 
    [Parameter(Mandatory = $false)][string] $include_sources=".*", 
    [Parameter(Mandatory = $false)][string] $exclude_sources="EXCLUDE NOTHING"
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

function Set-SourceVariables {
    param (
    [Parameter(Mandatory = $true)] $source,
    [Parameter(Mandatory = $false)] $properties = @("name","description","category")
    )

    # get any sumo env vars
    $sumo_env = dir env: | where {$_.name -match 'SUMO'}
    
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
                $source.$property = ($source.$property.tostring()).replace("{{$n}}","$v")
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

    if ($SyncSourcesPath) { 

        $arguments += "`"-VsyncSources=$SyncSourcesPath`""
    } else {
        $arguments += "`"-Vsources=$SourcesPath`""
    }

    # support various env variables
    IF ($ENV:SUMO_RECEIVER_URL) {  $ARGUMENTS += "`"-url=$($ENV:SUMO_RECEIVER_URL)`""} 
    #IF ($ENV:SUMO_PROXY_HOST) {  $ARGUMENTS += "`"-VproxyHost=$($ENV:SUMO_PROXY_HOST)`""} 
    #IF ($ENV:SUMO_PROXY_PORT) {  $ARGUMENTS += "`"-VproxyPort=$($ENV:SUMO_PROXY_PORT)`""} 
    IF ($ENV:SUMO_PROXY_USER) {  $ARGUMENTS += "`"-VproxyUser=$($ENV:SUMO_PROXY_USER)`""} 
    IF ($ENV:SUMO_PROXY_PASSWORD) {  $ARGUMENTS += "`"-VproxyPassword=$($ENV:SUMO_PROXY_PASSWORD)`""} 
    IF ($ENV:SUMO_PROXY_NTLM_DOMAIN) {  $ARGUMENTS += "`"-VproxyNtlmDomain=$($ENV:SUMO_RECEIVER_URL)`""} 
    IF ($ENV:SUMO_CLOBBER) {  $ARGUMENTS += "`"-Vclobber=$($ENV:SUMO_CLOBBER)`""} 
    #IF ($ENV:SUMO_DISABLE_SCRIPTS) {  $ARGUMENTS += "`"-VdisableScriptSource=$($ENV:SUMO_DISABLE_SCRIPTS)`""} 
    IF ($ENV:SUMO_JAVA_MEMORY_INIT) {  $ARGUMENTS += "`"-Vwrapper.java.initmemory=$($ENV:SUMO_JAVA_MEMORY_INIT)`""} 
    IF ($ENV:SUMO_JAVA_MEMORY_MAX) {  $ARGUMENTS += "`"-Vwrapper.java.maxmemory=$($ENV:SUMO_JAVA_MEMORY_MAX)`""} 
    #IF ($ENV:SUMO_EPHEMERAL) {  $ARGUMENTS += "`"-Vephemeral=$($ENV:SUMO_EPHEMERAL)`""} 
    IF ($ENV:SUMO_FIELDS) {  $ARGUMENTS += "`"-Vfields=$($ENV:SUMO_FIELDS)`""} 

    return $arguments
}

$commandArguments = Set-Arguments


#### SOURCE CONFIGURATION
# get the master file of all sources
$SourcesMasterList = Read-SourceLibrary -sources_library_path $source_library -return 'object'

# filter using include/exclude on name
$SourcesToLoad = Select-SourceLibrary -sources $SourcesMasterList.sources -include_sources $source_include -exclude_sources $source_exclude

$SourcesMasterList.sources = $SourcesToLoad 
$SourcesMasterList.sources = $SourcesMasterList.sources | foreach { Set-SourceVariables -source $_ }


#  Make sure syncsourcespath dir exists or sources if that was used.
if ($SyncSources) { 
    $sourcesFilePath = "$SyncSourcesPath/sumo.json"
    if (-not $Dryrun) { New-Item -ItemType directory -Path $SyncSourcesPath -force   | Out-Null}
}
else {
    $sourcesFilePath = "$SourcesPath/sumo.json"
    if (-not $Dryrun) { New-Item -ItemType directory -Path $SourcesPath -force | Out-Null }
}

if ($Dryrun) {
    write-host "sources config would be: $sourcesFilePath" 
    write-host ($SourcesMasterList | convertto-json -depth 20 )
} else {
    write-host "Creating $sourcesFilePath"
    $SourcesMasterList | convertto-json -depth 20 | out-file -FilePath "$sourcesFilePath" -Encoding ascii
}

######################### EXECUTE OR OUTPUT THE COMMAND ##############################
if ($Dryrun ) {
    Write-Host "Output command only:"
    Write-host "Install command: $localBinary $commandArguments"
}
else {
    write-host "downloading if necessary: $SumoBinary to $localBinary"
    if (test-path -path "$localBinary") {
       
    }
    else {  
        write-host "downloading: "
        $p = split-path -Path "$localBinary"
        New-Item -Path $p -ItemType Directory -force -ErrorAction SilentlyContinue | Out-Null
        Invoke-WebRequest -Uri $SumoBinary -OutFile "$localBinary" 
    }

    Write-Host "Executing: $localBinary..."
    Write-Verbose "Install command: $localBinary $commandArguments"
    $process = Start-Process -FilePath $localBinary -ArgumentList $commandArguments -Wait -PassThru
    if ($process.ExitCode -eq 0) {
        Write-Verbose "$localBinary has been successfully installed"
    }
    else {
        Write-Error "installer exit code  $($process.ExitCode) for file  $($exefile)"
    }

}

if ($removeInstallFile) { if (Test-Path $file) { Remove-Item $file }	}		

if ($VskipRegistration -and ($Dryrun -eq $false)) { 
    # prevent service starting on boot 
    # YOU MUST REVERT THIS IN YOUR STARTUP SCRIPT!!!
    Set-Service -Name sumo-collector -StartupType Manual
}

