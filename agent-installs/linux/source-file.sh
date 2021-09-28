# outpuf of file would be say /opt/SumoCollector/sources/sources.json

#dir=/opt/SumoCollector/sources
dir=.
mkdir -p $dir

cat > $dir/sources.json <<End-of-message
{
  "api.version": "v1",
  "sources": [
    {
        "name": "tmp_dummy",
        "description":"Track anything in dummy log for making test data",
        "category":"test/dummy",
        "automaticDateParsing":true,
        "multilineProcessingEnabled":false,
        "useAutolineMatching":true,
        "forceTimeZone":false,
        "filters":[],
        "cutoffTimestamp":0,
        "encoding":"UTF-8",
        "pathExpression":"/tmp/dummy.log",
        "blacklist":[],
        "sourceType":"LocalFile"
    }
  ]
}
End-of-message