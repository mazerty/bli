import hashlib
import logging
import os
import tempfile
import time

import boto3

region = "us-east-1"  # seems like we're stuck with the default zone for the whole stack to come together
root_domain = "mazerty.fr"
subdomain = "zebr0"
bucket_name = subdomain + "." + root_domain
source = "/home/ubuntu/workspace/zebr0-conf"

# deploy:
# create_certificate()
# wait_domain_validation_information()
# create_domain_validation_resource_record_set()
# wait_domain_validation_success()

# create_bucket()
# create_distribution()
# create_resource_record_set()


# undeploy:
# delete_resource_record_set()
# delete_distribution()
# delete_files()
# delete_bucket()

# delete_domain_validation_resource_record_set()
# delete_certificate()

logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger()

session = boto3.session.Session(region_name=region)
s3 = session.client(service_name="s3")
route53 = session.client(service_name="route53")
acm = session.client(service_name="acm")
cloudfront = session.client(service_name="cloudfront")


def check_bucket(_bucket_name=bucket_name):
    s3.head_bucket(Bucket=_bucket_name)


def create_bucket(_bucket_name=bucket_name):
    s3.create_bucket(Bucket=_bucket_name, ACL="public-read")
    s3.get_waiter("bucket_exists").wait(Bucket=_bucket_name)
    s3.put_bucket_website(Bucket=_bucket_name, WebsiteConfiguration={"IndexDocument": {"Suffix": "index.html"}})


def delete_bucket(_bucket_name=bucket_name):
    s3.delete_bucket(Bucket=_bucket_name)
    s3.get_waiter("bucket_not_exists").wait(Bucket=_bucket_name)


def _md5(path):
    md5 = hashlib.md5()
    with open(path, "rb") as file:
        for chunk in iter(lambda: file.read(4096), b""):
            md5.update(chunk)
    return md5.hexdigest()


def list_remote_files(_bucket_name=bucket_name):
    while True:
        response = s3.list_objects_v2(Bucket=_bucket_name)
        for item in response.get("Contents", []):
            if item.get("Size") != 0:
                yield item.get("Key"), s3.head_object(Bucket=_bucket_name, Key=item.get("Key")).get("Metadata", {}).get("md5", "")
        if not response.get("IsTruncated"):
            break


def list_local_files(_source=source):
    for dirpath, dirnames, filenames in os.walk(_source):
        # filter hidden directories, see https://stackoverflow.com/questions/19859840
        dirnames[:] = [d for d in dirnames if d[0] != "."]

        for filename in sorted(filenames):
            if filename[0] != ".":
                local_path = os.path.join(dirpath, filename)
                yield os.path.relpath(local_path, _source), _md5(local_path)


def upload_files(_bucket_name=bucket_name, _source=source):
    for file, md5 in list_local_files(_source):
        s3.upload_file(os.path.join(_source, file), _bucket_name, file, ExtraArgs={"ACL": "public-read", "Metadata": {"md5": md5}})
        s3.get_waiter("object_exists").wait(Bucket=_bucket_name, Key=file)


def download_files(_bucket_name=bucket_name, target=tempfile.mkdtemp()):
    for key, _ in list_remote_files(_bucket_name):
        local_path = os.path.join(target, key)
        os.makedirs(os.path.dirname(local_path), exist_ok=True)  # ensures that required subdirectories exist before downloading the object
        s3.download_file(_bucket_name, key, local_path)

    return target


def delete_files(_bucket_name=bucket_name):
    for key, _ in list_remote_files(_bucket_name):
        s3.delete_object(Bucket=_bucket_name, Key=key)
        s3.get_waiter("object_not_exists").wait(Bucket=_bucket_name, Key=key)


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
            "DefaultTTL": 0,
            "MinTTL": 0
        },
        "Comment": "",
        "PriceClass": "PriceClass_100",
        "Enabled": True,
        "ViewerCertificate": {"ACMCertificateArn": get_certificate_arn(), "SSLSupportMethod": "sni-only"}
    })
    time.sleep(10 * 60)  # the waiter below has a limited number of retries and it's not enough sometimes...
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
