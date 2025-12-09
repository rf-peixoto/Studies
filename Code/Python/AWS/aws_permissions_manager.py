#!/usr/bin/env python3
"""
pip install boto3 botocore

Features:
- Region optional (script works even if none is provided)
- Automatic region discovery via ec2.describe_regions
- Enumerates capabilities across all discovered regions:
      - EC2
      - Lambda
      - CloudWatch
      - S3 (global + region details)
- IAM & STS enumeration (global)
- Permission simulation (optional)
- Defensive error handling for denied permissions
"""

import argparse
import json
import sys
from typing import Dict, Any, List, Optional

import boto3
from botocore.exceptions import ClientError, NoCredentialsError, EndpointConnectionError


# =====================================================================
# Helper: Safe call wrapper
# =====================================================================

def safe_call(desc: str, func, **kwargs):
    """Safely execute AWS API calls and return None on access denied."""
    try:
        return func(**kwargs)
    except ClientError as e:
        code = e.response["Error"]["Code"]
        print(f"[!] {desc} failed ({code}): {e}", file=sys.stderr)
        return None
    except Exception as e:
        print(f"[!] Unexpected error in {desc}: {e}", file=sys.stderr)
        return None


# =====================================================================
# Main manager class
# =====================================================================

class AwsPermissionsManager:

    def __init__(self, access_key: str, secret_key: str, region: Optional[str] = None):
        self.access_key = access_key
        self.secret_key = secret_key
        self.region = region

        # Create a session *without* region unless provided
        if region:
            self.session = boto3.Session(
                aws_access_key_id=access_key,
                aws_secret_access_key=secret_key,
                region_name=region,
            )
        else:
            self.session = boto3.Session(
                aws_access_key_id=access_key,
                aws_secret_access_key=secret_key,
            )

        self.sts = self.session.client("sts")
        self.iam = self.session.client("iam")

        self.identity = None
        self.principal_arn = None
        self.principal_type = None
        self.account_id = None

    # ---------------------------------------------------------------
    # Identity
    # ---------------------------------------------------------------

    def get_identity(self):
        identity = safe_call("sts.get_caller_identity", self.sts.get_caller_identity)
        if not identity:
            print("[FATAL] Could not retrieve caller identity. Exiting.")
            sys.exit(1)

        self.identity = identity
        self.principal_arn = identity["Arn"]
        self.account_id = identity["Account"]

        # Classify principal
        if ":user/" in self.principal_arn:
            self.principal_type = "User"
        elif ":role/" in self.principal_arn or ":assumed-role/" in self.principal_arn:
            self.principal_type = "Role"
        else:
            self.principal_type = "Unknown"

        print("\n== Caller Identity ==")
        print(json.dumps(identity, indent=4))


    # ---------------------------------------------------------------
    # Region discovery
    # ---------------------------------------------------------------

    def discover_regions(self) -> List[str]:
        """
        Uses STS-global credentials to safely create an EC2 client
        for region discovery.
        """
        print("\n[*] Discovering enabled AWS regions...")

        # EC2 is region-scoped; choose a default region if none exists
        temp_region = self.session.region_name or "us-east-1"

        ec2 = boto3.client(
            "ec2",
            aws_access_key_id=self.access_key,
            aws_secret_access_key=self.secret_key,
            region_name=temp_region,
        )

        resp = safe_call("ec2.describe_regions", ec2.describe_regions)
        if not resp:
            print("[!] Could not enumerate regions. Using default us-east-1 only.")
            return [temp_region]

        regions = sorted([r["RegionName"] for r in resp["Regions"]])
        print(f"[+] Regions discovered: {regions}")
        return regions


    # ---------------------------------------------------------------
    # Service enumeration per region
    # ---------------------------------------------------------------

    def enumerate_ec2(self, region: str) -> Dict[str, Any]:
        ec2 = boto3.client(
            "ec2",
            aws_access_key_id=self.access_key,
            aws_secret_access_key=self.secret_key,
            region_name=region,
        )
        out = {}

        print(f"    [EC2] Checking region {region}")

        # Instances
        resp = safe_call("DescribeInstances", ec2.describe_instances)
        if resp is not None:
            out["instances"] = resp.get("Reservations", [])

        # Security Groups
        resp = safe_call("DescribeSecurityGroups", ec2.describe_security_groups)
        if resp is not None:
            out["security_groups"] = resp.get("SecurityGroups", [])

        # Key pairs
        resp = safe_call("DescribeKeyPairs", ec2.describe_key_pairs)
        if resp is not None:
            out["key_pairs"] = resp.get("KeyPairs", [])

        return out


    def enumerate_lambda(self, region: str) -> Dict[str, Any]:
        lam = boto3.client(
            "lambda",
            aws_access_key_id=self.access_key,
            aws_secret_access_key=self.secret_key,
            region_name=region,
        )
        out = {}

        print(f"    [Lambda] Checking region {region}")

        resp = safe_call("ListFunctions", lam.list_functions)
        if resp is not None:
            out["functions"] = resp.get("Functions", [])

        return out


    def enumerate_cloudwatch(self, region: str) -> Dict[str, Any]:
        cw = boto3.client(
            "cloudwatch",
            aws_access_key_id=self.access_key,
            aws_secret_access_key=self.secret_key,
            region_name=region,
        )
        out = {}

        print(f"    [CloudWatch] Checking region {region}")

        resp = safe_call("ListMetrics", cw.list_metrics)
        if resp is not None:
            out["metrics_count"] = len(resp.get("Metrics", []))

        return out


    def enumerate_s3_global(self) -> Dict[str, Any]:
        s3 = boto3.client(
            "s3",
            aws_access_key_id=self.access_key,
            aws_secret_access_key=self.secret_key,
        )
        out = {}

        print("    [S3] Listing buckets (global)")

        resp = safe_call("ListBuckets", s3.list_buckets)
        if resp is not None:
            out["buckets"] = resp.get("Buckets", [])

        return out


    # ---------------------------------------------------------------
    # Region orchestrator
    # ---------------------------------------------------------------

    def enumerate_multi_region_capabilities(self, regions: List[str]) -> Dict[str, Any]:
        print("\n== Enumerating regional service capabilities ==")

        results = {"regions": {}}

        # Global S3
        results["s3_global"] = self.enumerate_s3_global()

        # Per-region modules
        for region in regions:
            print(f"\n[+] Region: {region}")
            results["regions"][region] = {
                "ec2": self.enumerate_ec2(region),
                "lambda": self.enumerate_lambda(region),
                "cloudwatch": self.enumerate_cloudwatch(region),
            }

        return results


# =====================================================================
# CLI
# =====================================================================

def parse_args():
    p = argparse.ArgumentParser(description="AWS Capability & Permission Manager with Auto-Region Discovery")
    p.add_argument("--access-key", required=True)
    p.add_argument("--secret-key", required=True)
    p.add_argument("--region", help="Optional default region. If omitted, script discovers regions automatically.")
    return p.parse_args()


def main():
    args = parse_args()
    mgr = AwsPermissionsManager(args.access_key, args.secret_key, args.region)

    mgr.get_identity()
    regions = mgr.discover_regions()

    result = mgr.enumerate_multi_region_capabilities(regions)

    print("\n== Final Capability Enumeration ==")
    print(json.dumps(result, indent=4))


if __name__ == "__main__":
    main()
