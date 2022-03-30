 # cats a file to STDOUT 
# Might be useful in rare circumstances to send to sumo via a script source
# Say where you want to send file(s) newer than a certain time to sumo on a schedule
# one exampe use case is where daily files have very large duplicated headers so checksum in local files source sees them as identical.

# Configure $pattern and $path to pick the files
$pattern = "*.txt" 
$path = 'C:\Sumo\SumoLogicCollector\scripts' # defaults to scriptdir
# hours is the age of files to check for using pattern above
$hours=-24

$scriptDir = Split-Path -Path $MyInvocation.MyCommand.Definition -Parent
if ($path ) {} else {$path = $scriptDir}

$filepath="$path/$pattern"

$files = Get-ChildItem -Path $filepath | Where-Object {$_.LastWriteTime -ge (Get-Date).AddHours($hours)}

write-host "(get-date).toString("yyyy/MM/dd HH:mm:ss zzz") Starting File Check Script. path=$path -ge $hours hours matchingfiles=$($files.Count)" 

foreach ($file in $files) {
    write-host "Parsing file: $file"
    $data = get-content -Path "$($file.fullname)"# -Raw
    foreach ($line in $data) {
    write-host "$( ($file.LastWriteTime).toString("yyyy/MM/dd HH:mm:ss zzz")) EVENT=$line FILE=$($file.name)"
    }
} 
