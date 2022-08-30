# Cloudwatch EC2 dashbaords to use in sumo if you setup a cloudwatch EC2 source. 
Stack linked to 'instanceid' so will render in AWSO Explore.
- apps/AWS-EC2/aws-ec2-cloudwatch-overview.json - 'overview' with clickable honeycomb to drill down that will link to the 'EC2' namespace level i explore
- apps/AWS-EC2/aws-ec2-cloudwatch.json - a 'node level' ec2 dashboard with detailed graphs for each Cloudwatch EC2 metric. Stack linked to the 'instanceid' level of explore.

Both dashboards have a 'field' and 'value' filter than you can use with custom metric dimensions. This demonstrates how it's easy to build your own custom dashboards that use your own tagging dimensions on your cloudwatch metrics.

If you follow the AWS Observability instructions the metrics hierarchy for EC2 is generated from Sumo Logic host metrics - NOT Cloudwatch EC2 metrics.

Some extra tagging in Sumo config adds the 'namespace=AWS/EC2' tag to host metrics so they appear to have come from AWS when in fact they come from a Sumo agent with a host metrics source.

This doc describes how the 'account' tag gets added to host metrics to setup AWSO https://help.sumologic.com/Observability_Solution/AWS_Observability_Solution/03_Other_Configurations_and_Tools/Add_Fields_to_Existing_Host_Metrics_Sources

One might also want to use native Cloudwatch EC2 metrics along with or instead of host metrics in AWSO and explore.

## What native EC2 Cloudwatch metrics are there?
Cloudwatch metrics for the AWS/EC2 namespace, they will be reported to Sumo Logic if configured with whatever tags exist on each EC2 as metric dimensions. It's important to note that host metrics provide better granularity and more metrics than Cloudwatch (such as disk space and memory use).

https://docs.aws.amazon.com/AWSEC2/latest/UserGuide/viewing_metrics_with_cloudwatch.html

Cloudwatch EC2 provides some metrics that are not available in host metrics:
- CPU credits (for types that have credits)
- Status Check Fail ( a rarely occurring indicator that the AWS hypervisor host or the instance is in a failed state)

## How Can I Collect Cloudwatch AWS EC2 Metrics in Sumo so they work in AWSO?
There are several ways to collect EC2 metrics from Cloudwatch.

Update your AWSO stack or terraform for each account/region to include the namespace parameter in option 4. 

Add a cloudwatch metrics source for the EC2 namespace manually or via the API: https://help.sumologic.com/03Send-Data/Sources/02Sources-for-Hosted-Collectors/Amazon-Web-Services/Amazon-CloudWatch-Source-for-Metrics. Add an 'account' tag manually for the account name in AWSO on the source
Add a cloudwatch metrics kinesis source for the EC2 namespace https://help.sumologic.com/03Send-Data/Sources/02Sources-for-Hosted-Collectors/Amazon-Web-Services/AWS_Kinesis_Firehose_for_Metrics_Source Add an 'account' tag manually for the account name in AWSO on the source

