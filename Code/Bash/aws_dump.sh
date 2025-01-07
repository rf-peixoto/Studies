# Download all the content from a s# bucket. If the url is s3://name.s3.amazonaws.com/ bucket name is just 'name'
aws s3 sync s3://<bucket name> output_folder --no-sign-request
