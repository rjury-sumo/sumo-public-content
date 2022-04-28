<#
        .SYNOPSIS
        Checks number of files matching a path or < > file age in minutes.

        .DESCRIPTION
        Checks number of files matching a path or < > file age in minutes.
        Intended for use to ouput log lines ot ingest into Sumo Logic either via:
        - STDOUT if this was running as a script check
        - posting to an HTTPS source endpint address

        The checks to run should be defined in filechecks.json or passed as a text object in JSON format using jsonchecks parameter.

        Check format is as below
        Check can be one for FileCount,FilesOlderThan or FilesNewerThan
        If using the files Older or Newer set the age_minutes to a value otherwise use 0.
        Checkpath is the file path to match. This can be local (in which case it's evaluated as relative to scriptdir) or full path.
        {
        "checks": [
            {
                "threshold": 0,
                "check": "FileCount",
                "operator": "eq",
                "checkpath": "*.out",
                "age_minutes": 0
                }
            ]
        }

        .PARAMETER application
        Optional application name to include in the output message.

        .PARAMETER outputpath
        if using the FILE output this the path to output to. Default $ScriptDir/$ScriptName.out

        .PARAMETER output
        output to produce: "STDOUT","TEST","FILE","HTTPS", defaults STDOUT

        .PARAMETER SUMO_URL
        If using HTTPS output this should be the HTTPS source URL.

        .PARAMETER source_category
        The source category to use (applied to HTTPS only)

        .PARAMETER computer
        defaults to local host name but can be overridden 

        .PARAMETER jsoncheckfile
        A local file containing a JSON checks array of checks to run.
        Use this OR jsonchecks
        
        .PARAMETER jsonchecks
        Pass the JSON checks array as a parameter instead of using jsoncheckfile

        .EXAMPLE
        PS> file-check.ps1  
        Run the default list of checks in filechecks.json and output to STDOUT

        .EXAMPLE
    #>

Param (
    $application = "None",  # an application / category stringRN
    $outputpath , # optional path to File if using out method. will default to cwd/script.out
    [ValidateSet("STDOUT","TEST","FILE","HTTPS")] $output = "STDOUT", # output format
    $SUMO_URL = $env:SUMO_ENDPOINT, # optional HTTPS SUMO endpoint to post results to
    $sumo_category = 'sreteam/custom_check',
    $computer = [Environment]::MachineName,

    # jsonchecksfile
    $jsoncheckfile = "filechecks.json",

    #  send an array of checks in JSON format directly as an arg
    #$jsonchecks = '{ "checks": [{"threshold":0,"check":"FileCount","operator":"eq","checkpath":"*.out","age_minutes":0}]} '
    $jsonchecks # ='{"checks":[{"threshold":0,"check":"FileCount","operator":"eq","checkpath":"*.out","age_minutes":0},{"threshold":0,"check":"FilesOlderThan","operator":"gt","checkpath":"*.out","age_minutes":15},{"threshold":0,"check":"FilesNewerThan","operator":"gt","checkpath":"*.out","age_minutes":15}]}'
)

$scriptDir = Split-Path -Path $MyInvocation.MyCommand.Definition -Parent
$script = Split-Path -Path $MyInvocation.MyCommand.Definition -Leaf

if ($jsonchecks) {
    $checkdb = ($jsonchecks | ConvertFrom-Json)
}
else {
    $checkdb = Get-Content -Path "$scriptDir/$jsoncheckfile" -Raw |convertfrom-json
    write-host "found: $($checkdb.checks.Count) checks in: $jsoncheckfile"
}

if ($checkdb.checks) {} else { Write-Error "no checks found. Supply a valid object via jsoncheckfile or jsonchecks params."; exit 1}

foreach ($c in $checkdb.checks) {
    # check specific fields
    $check = $c.check
    $threshold = $c.threshold
    $age_minutes = $c.age_minutes
    $operator = $c.operator 
    $checkpath = $c.checkpath
        
        if ($checkpath) {
            if (Split-Path -Path $checkpath -Parent) {
                # path is full path
            
            } else {
                # path is defined relative to cwd
               $checkpath = "$scriptDir/$checkpath"
            }
        
        } else  {Write-Error "mandatory checkpath variable not set"; exit 1}
        
        if ($outputpath) {
            # output path is defined
        
        } else {$outputpath = "$scriptDir/$application.$check.$computer.out"}
        
        $date = (get-date).toString("yyyy/MM/dd HH:mm:ss zzz")
        
        Write-Verbose "OS: $($Env:OS) 'nhost: $computer'nlevel: $status'ncheck: $check'napplication: $application'n: outputpath: $outputpath'ncheckdescription: $checkdescription 'nthreshold: $threshold 'noperator: $operator'noutput: $output'nSUMO_URL: $SUMO_URL"
        #Write-Verbose "OS: $($Env:OS)'nhost: $computer'nlevel: $status'ncheck: $check'napplication: $application'n: outputpath: $outputpath'ncheckdescription: $checkdescription 'nthreshold: $threshold 'noperator: $operator'noutput: $output'nSUMO_URL: $SUMO_URL"
        
        if ($check -eq "FileCount") {
            $Files = Get-ChildItem -Path "$checkpath" 
            $CheckValue = $files.Count
            $CheckDescription = "Count of files path: $checkpath. Value: $checkvalue Threshold: $operator $threshold"  # Description for check
          
        } elseif ($check -eq "FilesOlderThan") {
            $Files = Get-ChildItem -Path "$checkpath" | ? { $_.LastWriteTime -gt (Get-Date).AddMinutes(0 - $age_minutes)}
            $CheckValue = $files.Count
            $CheckDescription = "Count of files > $age_minutes minutes old,path: $checkpath. Value: $checkvalue Threshold: $operator $threshold"  # Description for check
        
        } elseif ($check -eq "FilesNewerThan") {
            $Files = Get-ChildItem -Path "$checkpath" | ? { $_.LastWriteTime -lt (Get-Date).AddMinutes(0 - $age_minutes)}
            $CheckValue = $files.Count
            $CheckDescription = "Count of files < $age_minutes minutes old, path: $checkpath. Value: $checkvalue Threshold: $operator $threshold"  # Description for check
        } else {
            Write-Error "invalid check type defined: $check "; exit 1
        }
        $status = "OK"

        if ($operator -eq 'lt') {
            if ($CheckValue -lt $threshold) {
                $status = 'ERROR'
            }
        } elseif ($operator -eq 'gt' ) {
            if ($CheckValue -gt $threshold) {
                $status = 'ERROR'
            }
        } elseif ($operator -eq 'eq' ) {
            if ($CheckValue -eq $threshold) {
                $status = 'ERROR'
            }
        } elseif ($operator -eq 'le' ) {
            if ($CheckValue -le $threshold) {
                $status = 'ERROR'
            }
        } elseif ($operator -eq 'ge' ) {
            if ($CheckValue -ge $threshold) {
                $status = 'ERROR'
            }
        }  else {
            Write-Error "invalid operator type defined: $operator "; exit 1
        }
        
        $text = "$date $status Host: $computer App: $application Check: $check Description: $CheckDescription"
        Write-Verbose $text
        
        if ($output -eq 'TEST') {
            write-host $text
        }
        elseif ($output -eq 'STDOUT') {
            Write-Output $text
        }
        elseif ($output -eq 'FILE') {
            # simple log rotation model, roll at max size
            $max_file_bytes = 1000
            $mode = 'overwrite'
            if (Get-ChildItem -Path $outputpath -ErrorAction SilentlyContinue ) {
                # new file
                $bytes = (get-ChildItem -Path $outputpath).Length 
                if ( $bytes -lt $max_file_bytes) {
                    Write-Verbose "found file append $bytes -lt $max_file_bytes"
                    $mode = 'append'
                } else  {
                    Write-Verbose "found file overwrite: $bytes -gt $max_file_bytes"
                }
            } 
        
            if ($mode -eq 'overwrite') {
                $text | Out-File -FilePath $outputpath -Encoding ascii -Force
            }
            else {
                $text | Out-File -FilePath $outputpath -Encoding ascii -Append
            }
            Write-Verbose "mode: $mode $outputpath"
        }
        elseif ($output -eq 'HTTPS') {
            # some code here to invoke-webrequest to sumo https endpoint
            $response = Invoke-WebRequest -Method POST -Body $text $SUMO_URL -Headers @{'X-Sumo-Category' = $sumo_category} 
        } else {
            write-host $text
        }
}
