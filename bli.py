import logging
import mimetypes
import os
import tempfile
import time

import boto3

region = "us-east-1"  # seems like we're stuck with the default zone for the whole stack to come together
root_domain = "mazerty.fr"
subdomain = "mirror"
bucket_name = subdomain + "." + root_domain

logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger()

session = boto3.session.Session(region_name=region)
s3 = session.client(service_name="s3")
route53 = session.client(service_name="route53")
acm = session.client(service_name="acm")
cloudfront = session.client(service_name="cloudfront")


def check_bucket():
    s3.head_bucket(Bucket=bucket_name)


def create_bucket():
    s3.create_bucket(Bucket=bucket_name, ACL="public-read")
    s3.get_waiter("bucket_exists").wait(Bucket=bucket_name)
    s3.put_bucket_website(Bucket=bucket_name, WebsiteConfiguration={"IndexDocument": {"Suffix": "index.html"}})


def delete_bucket():
    s3.delete_bucket(Bucket=bucket_name)
    s3.get_waiter("bucket_not_exists").wait(Bucket=bucket_name)


def upload_files():
    source = "upload"
    for dirpath, _, filenames in os.walk(source):
        for filename in filenames:
            local_path = os.path.join(dirpath, filename)
            relative_path = os.path.relpath(local_path, source)
            s3.upload_file(local_path, bucket_name, relative_path, ExtraArgs={"ACL": "public-read", "ContentType": mimetypes.guess_type(local_path)[0]})
            s3.get_waiter("object_exists").wait(Bucket=bucket_name, Key=relative_path)


def download_files():
    target = tempfile.mkdtemp()
    while True:
        response = s3.list_objects_v2(Bucket=bucket_name)
        for item in response.get("Contents", []):
            if item.get("Size") != 0:
                local_path = os.path.join(target, item.get("Key"))
                os.makedirs(os.path.dirname(local_path), exist_ok=True)  # ensures that required subdirectories exist before downloading the object
                s3.download_file(bucket_name, item.get("Key"), local_path)
        if not response.get("IsTruncated"):
            break
    return target


def delete_files():
    while True:
        response = s3.list_objects_v2(Bucket=bucket_name)
        for item in response.get("Contents", []):
            s3.delete_object(Bucket=bucket_name, Key=item.get("Key"))
            s3.get_waiter("object_not_exists").wait(Bucket=bucket_name, Key=item.get("Key"))
        if not response.get("IsTruncated"):
            break


def get_certificate_arn():
    for item in acm.list_certificates().get("CertificateSummaryList", []):
        if item.get("DomainName") == bucket_name:
            return item.get("CertificateArn")


def get_certificate(arn):
    return acm.describe_certificate(CertificateArn=arn).get("Certificate")


def create_certificate():
    acm.request_certificate(DomainName=bucket_name, ValidationMethod="DNS")


def wait_domain_validation_information():
    arn = get_certificate_arn()
    while not get_certificate(arn).get("DomainValidationOptions")[0].get("ResourceRecord"):
        time.sleep(10)


def wait_domain_validation_success():  # the boto3 version in ubuntu repositories doesn't include the waiter yet
    arn = get_certificate_arn()
    while get_certificate(arn).get("DomainValidationOptions")[0].get("ValidationStatus") != "SUCCESS":
        time.sleep(10)


def delete_certificate():
    acm.delete_certificate(CertificateArn=get_certificate_arn())


def get_hosted_zone_id():
    hosted_zones = route53.list_hosted_zones_by_name(DNSName=root_domain + ".", MaxItems="1").get("HostedZones")
    if hosted_zones and hosted_zones[0].get("Name") == root_domain + ".":
        return hosted_zones[0].get("Id")


def get_resource_record_set():
    resource_record_sets = route53.list_resource_record_sets(
        HostedZoneId=get_hosted_zone_id(),
        StartRecordName=bucket_name + ".",
        StartRecordType="A",
        MaxItems="1"
    ).get("ResourceRecordSets")
    if resource_record_sets and resource_record_sets[0].get("Name") == bucket_name + ".":
        return resource_record_sets[0]


def create_resource_record_set():
    response = route53.change_resource_record_sets(
        HostedZoneId=get_hosted_zone_id(),
        ChangeBatch={"Changes": [{
            "Action": "CREATE",
            "ResourceRecordSet": {
                "Name": bucket_name + ".",
                "Type": "A",
                "AliasTarget": {
                    "DNSName": get_distribution().get("DomainName"),
                    "HostedZoneId": "Z2FDTNDATAQYW2",  # doesn't seem there's an api to fetch the hostedzoneid for a specific region/service
                    "EvaluateTargetHealth": False
                }
            }
        }]}
    )
    route53.get_waiter("resource_record_sets_changed").wait(Id=response.get("ChangeInfo").get("Id"))


def delete_resource_record_set(rrs_getter=get_resource_record_set):
    response = route53.change_resource_record_sets(
        HostedZoneId=get_hosted_zone_id(),
        ChangeBatch={"Changes": [{
            "Action": "DELETE",
            "ResourceRecordSet": rrs_getter()
        }]}
    )
    route53.get_waiter("resource_record_sets_changed").wait(Id=response.get("ChangeInfo").get("Id"))


def get_domain_validation_resource_record_set():
    name = get_certificate(get_certificate_arn()).get("DomainValidationOptions")[0].get("ResourceRecord").get("Name")
    resource_record_sets = route53.list_resource_record_sets(
        HostedZoneId=get_hosted_zone_id(),
        StartRecordName=name,
        StartRecordType="CNAME",
        MaxItems="1"
    ).get("ResourceRecordSets")
    if resource_record_sets and resource_record_sets[0].get("Name") == name:
        return resource_record_sets[0]


def create_domain_validation_resource_record_set():
    resource_record = get_certificate(get_certificate_arn()).get("DomainValidationOptions")[0].get("ResourceRecord")
    response = route53.change_resource_record_sets(
        HostedZoneId=get_hosted_zone_id(),
        ChangeBatch={"Changes": [{
            "Action": "CREATE",
            "ResourceRecordSet": {
                "Name": resource_record.get("Name"),
                "Type": "CNAME",
                "ResourceRecords": [{
                    "Value": resource_record.get("Value")
                }],
                "TTL": 300
            }
        }]}
    )
    route53.get_waiter("resource_record_sets_changed").wait(Id=response.get("ChangeInfo").get("Id"))


def delete_domain_validation_resource_record_set():
    delete_resource_record_set(get_domain_validation_resource_record_set)


def get_distribution():
    for item in cloudfront.list_distributions().get("DistributionList").get("Items", []):
        if item.get("Aliases").get("Items")[0] == bucket_name:
            return item


def create_distribution():
    response = cloudfront.create_distribution(DistributionConfig={
        "CallerReference": str(time.time()),
        "Aliases": {"Quantity": 1, "Items": [bucket_name]},
        "DefaultRootObject": "index.html",
        "Origins": {
            "Quantity": 1,
            "Items": [{
                "Id": "1",
                "DomainName": bucket_name + ".s3.amazonaws.com",
                "S3OriginConfig": {"OriginAccessIdentity": ""}  # error 500 if missing
            }]
        },
        "DefaultCacheBehavior": {
            "TargetOriginId": "1",
            "ForwardedValues": {"QueryString": False, "Cookies": {"Forward": "none"}},
            "TrustedSigners": {"Enabled": False, "Quantity": 0},
            "ViewerProtocolPolicy": "redirect-to-https",
            "MinTTL": 0
        },
        "Comment": "",
        "PriceClass": "PriceClass_100",
        "Enabled": True,
        "ViewerCertificate": {"ACMCertificateArn": get_certificate_arn(), "SSLSupportMethod": "sni-only"}
    })
    cloudfront.get_waiter("distribution_deployed").wait(Id=response.get("Distribution").get("Id"))


def delete_distribution():
    distribution_id = get_distribution().get("Id")

    # first we need to disable the distribution
    response = cloudfront.get_distribution_config(Id=distribution_id)
    response.get("DistributionConfig")["Enabled"] = False
    disabled_etag = cloudfront.update_distribution(
        DistributionConfig=response.get("DistributionConfig"),
        Id=distribution_id,
        IfMatch=response.get("ETag")
    ).get("ETag")
    cloudfront.get_waiter("distribution_deployed").wait(Id=distribution_id)

    # then we can delete it
    cloudfront.delete_distribution(Id=distribution_id, IfMatch=disabled_etag)


def deploy():
    create_bucket()
    if not get_certificate_arn():
        create_certificate()
    wait_domain_validation_information()
    if not get_domain_validation_resource_record_set():
        create_domain_validation_resource_record_set()
    wait_domain_validation_success()
    if not get_distribution():
        create_distribution()
    if not get_resource_record_set():
        create_resource_record_set()


def undeploy():
    if get_resource_record_set():
        delete_resource_record_set()
    if get_distribution():
        delete_distribution()
    if get_domain_validation_resource_record_set():
        delete_domain_validation_resource_record_set()
    if get_certificate_arn():
        delete_certificate()
    delete_files()
    delete_bucket()
