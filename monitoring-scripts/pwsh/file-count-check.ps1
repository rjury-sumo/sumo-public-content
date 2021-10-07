Param ($checkpath = "./*", 
    $level = "INFO",  # default level
    $check = "FileCount",  # name of this check
    $application = "myapp",  # an application / category string
    $outputpath = "custom-checks.txt", # path to file if using FILE output
    $CheckDescription = "Count of files",  # Description for check
    $threshold = 0, # value to compare
    [ValidateSet('gt','lt','eq')] $operator = 'lt', # validation operator
    [ValidateSet("STDOUT","TEST","FILE","HTTPS")] $output = "STDOUT", # output format
    $SUMO_URL = $env:SUMO_URL, # for HTTPS output the endpoint url
    $sumo_category = 'sreteam/custom_check'
)

$computer = hostname
$date = Get-Date -Format "yyyy-MM-dd hh:mm:ss zzzz"
Write-Verbose "OS: $($Env:OS)`nhost: $computer`nlevel: $level`ncheck: $check`napplication: $application`n: outputpath: $outputpath`ncheckdescription: $checkdescription `nthreshold: $threshold `noperator: $operator`noutput: $output`nSUMO_URL: $SUMO_URL"

$Files = Get-ChildItem -Path "$checkpath" 
$CheckValue = $files.Count

if ($operator -eq 'lt') {
    if ($CheckValue -lt $threshold) {
        $level = 'ERROR'
    }
} elseif ($operator -eq 'eq' ) {
    if ($CheckValue -ne $threshold) {
        $level = 'ERROR'
    }
} else {
    if ($CheckValue -gt $threshold) {
        $level = 'ERROR'
    }  
}

$text = "$date $level $computer $application $check $CheckDescription for path: $($checkpath) is: $CheckValue files is $operator threshold: $threshold"
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
    Invoke-WebRequest -Method POST -Body $text $SUMO_URL -Headers @{'X-Sumo-Category' = $sumo_category} 
}



