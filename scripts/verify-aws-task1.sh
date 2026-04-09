#!/usr/bin/env bash
set -euo pipefail

TERRAFORM_DIR="infra/aws/task1-foundation"

usage() {
  cat <<'EOF_USAGE'
Usage: bash scripts/verify-aws-task1.sh [--terraform-dir DIR]

Verification order:
1. resolve identifiers from environment variables or Terraform outputs
2. verify the ECR repository exists
3. verify the S3 bucket exists and is writable
4. verify subnet tiers and route tables match the intended public/private split
5. verify ECS / RDS / inference security groups are not publicly exposed
6. verify the backend API domain resolves over HTTPS

You can either:
- run from the repo root after `terraform apply`, or
- export the needed values manually if Terraform state is elsewhere

Optional flags:
  --terraform-dir DIR   Terraform module directory (default: infra/aws/task1-foundation)
  -h, --help            Show this help text

Environment overrides:
  SUPPORTDOC_TASK1_AWS_REGION
  SUPPORTDOC_TASK1_BACKEND_API_DOMAIN
  SUPPORTDOC_TASK1_ECR_REPOSITORY_NAME
  SUPPORTDOC_TASK1_S3_BUCKET_NAME
  SUPPORTDOC_TASK1_ALB_SECURITY_GROUP_ID
  SUPPORTDOC_TASK1_ECS_SECURITY_GROUP_ID
  SUPPORTDOC_TASK1_RDS_SECURITY_GROUP_ID
  SUPPORTDOC_TASK1_INFERENCE_SECURITY_GROUP_ID
  SUPPORTDOC_TASK1_PUBLIC_ROUTE_TABLE_ID
  SUPPORTDOC_TASK1_APP_PRIVATE_ROUTE_TABLE_ID
  SUPPORTDOC_TASK1_DATA_PRIVATE_ROUTE_TABLE_ID
  SUPPORTDOC_TASK1_PUBLIC_SUBNET_IDS        comma-separated
  SUPPORTDOC_TASK1_APP_PRIVATE_SUBNET_IDS   comma-separated
  SUPPORTDOC_TASK1_DATA_PRIVATE_SUBNET_IDS  comma-separated
EOF_USAGE
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --terraform-dir)
      TERRAFORM_DIR="$2"
      shift 2
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      echo "Unknown argument: $1" >&2
      usage >&2
      exit 1
      ;;
  esac
done

require_command() {
  local name="$1"
  if ! command -v "$name" >/dev/null 2>&1; then
    echo "Required command not found: $name" >&2
    exit 1
  fi
}

require_non_blank() {
  local name="$1"
  local value="$2"
  if [[ -z "${value// }" ]]; then
    echo "Missing required value: ${name}" >&2
    exit 1
  fi
}

tf_raw() {
  local output_name="$1"
  if ! command -v terraform >/dev/null 2>&1; then
    return 0
  fi
  if [[ ! -d "${TERRAFORM_DIR}" ]]; then
    return 0
  fi
  terraform -chdir="${TERRAFORM_DIR}" output -raw "${output_name}" 2>/dev/null || true
}

csv_or_tf_list() {
  local env_value="$1"
  local tf_output_name="$2"
  if [[ -n "${env_value// }" ]]; then
    printf '%s' "${env_value}"
    return 0
  fi
  if ! command -v terraform >/dev/null 2>&1 || [[ ! -d "${TERRAFORM_DIR}" ]]; then
    return 0
  fi
  local json_payload
  json_payload="$(terraform -chdir="${TERRAFORM_DIR}" output -json "${tf_output_name}" 2>/dev/null || true)"
  if [[ -z "${json_payload// }" ]]; then
    return 0
  fi
  JSON_PAYLOAD="${json_payload}" python - <<'PY'
from __future__ import annotations
import json
import os
payload = json.loads(os.environ["JSON_PAYLOAD"])
if isinstance(payload, list):
    print(",".join(str(item) for item in payload))
PY
}

map_or_tf_field() {
  local env_value="$1"
  local tf_output_name="$2"
  local field_name="$3"
  if [[ -n "${env_value// }" ]]; then
    printf '%s' "${env_value}"
    return 0
  fi
  if ! command -v terraform >/dev/null 2>&1 || [[ ! -d "${TERRAFORM_DIR}" ]]; then
    return 0
  fi
  local json_payload
  json_payload="$(terraform -chdir="${TERRAFORM_DIR}" output -json "${tf_output_name}" 2>/dev/null || true)"
  if [[ -z "${json_payload// }" ]]; then
    return 0
  fi
  JSON_PAYLOAD="${json_payload}" FIELD_NAME="${field_name}" python - <<'PY'
from __future__ import annotations
import json
import os
payload = json.loads(os.environ["JSON_PAYLOAD"])
field_name = os.environ["FIELD_NAME"]
value = payload.get(field_name, "")
if value is None:
    value = ""
print(value)
PY
}

AWS_REGION="${SUPPORTDOC_TASK1_AWS_REGION:-$(tf_raw aws_region)}"
BACKEND_API_DOMAIN="${SUPPORTDOC_TASK1_BACKEND_API_DOMAIN:-$(tf_raw backend_api_domain)}"
ECR_REPOSITORY_NAME="${SUPPORTDOC_TASK1_ECR_REPOSITORY_NAME:-$(tf_raw ecr_repository_name)}"
S3_BUCKET_NAME="${SUPPORTDOC_TASK1_S3_BUCKET_NAME:-$(tf_raw artifact_bucket_name)}"

ALB_SECURITY_GROUP_ID="${SUPPORTDOC_TASK1_ALB_SECURITY_GROUP_ID:-$(map_or_tf_field "" security_group_ids alb)}"
ECS_SECURITY_GROUP_ID="${SUPPORTDOC_TASK1_ECS_SECURITY_GROUP_ID:-$(map_or_tf_field "" security_group_ids ecs)}"
RDS_SECURITY_GROUP_ID="${SUPPORTDOC_TASK1_RDS_SECURITY_GROUP_ID:-$(map_or_tf_field "" security_group_ids rds)}"
INFERENCE_SECURITY_GROUP_ID="${SUPPORTDOC_TASK1_INFERENCE_SECURITY_GROUP_ID:-$(map_or_tf_field "" security_group_ids inference)}"

PUBLIC_ROUTE_TABLE_ID="${SUPPORTDOC_TASK1_PUBLIC_ROUTE_TABLE_ID:-$(map_or_tf_field "" route_table_ids public)}"
APP_PRIVATE_ROUTE_TABLE_ID="${SUPPORTDOC_TASK1_APP_PRIVATE_ROUTE_TABLE_ID:-$(map_or_tf_field "" route_table_ids app_private)}"
DATA_PRIVATE_ROUTE_TABLE_ID="${SUPPORTDOC_TASK1_DATA_PRIVATE_ROUTE_TABLE_ID:-$(map_or_tf_field "" route_table_ids data_private)}"

PUBLIC_SUBNET_IDS="$(csv_or_tf_list "${SUPPORTDOC_TASK1_PUBLIC_SUBNET_IDS:-}" public_subnet_ids)"
APP_PRIVATE_SUBNET_IDS="$(csv_or_tf_list "${SUPPORTDOC_TASK1_APP_PRIVATE_SUBNET_IDS:-}" app_private_subnet_ids)"
DATA_PRIVATE_SUBNET_IDS="$(csv_or_tf_list "${SUPPORTDOC_TASK1_DATA_PRIVATE_SUBNET_IDS:-}" data_private_subnet_ids)"

require_command aws
require_command curl
require_command python

require_non_blank "AWS region" "${AWS_REGION}"
require_non_blank "backend API domain" "${BACKEND_API_DOMAIN}"
require_non_blank "ECR repository name" "${ECR_REPOSITORY_NAME}"
require_non_blank "S3 bucket name" "${S3_BUCKET_NAME}"
require_non_blank "ALB security group id" "${ALB_SECURITY_GROUP_ID}"
require_non_blank "ECS security group id" "${ECS_SECURITY_GROUP_ID}"
require_non_blank "RDS security group id" "${RDS_SECURITY_GROUP_ID}"
require_non_blank "inference security group id" "${INFERENCE_SECURITY_GROUP_ID}"
require_non_blank "public route table id" "${PUBLIC_ROUTE_TABLE_ID}"
require_non_blank "app private route table id" "${APP_PRIVATE_ROUTE_TABLE_ID}"
require_non_blank "data private route table id" "${DATA_PRIVATE_ROUTE_TABLE_ID}"
require_non_blank "public subnet ids" "${PUBLIC_SUBNET_IDS}"
require_non_blank "app private subnet ids" "${APP_PRIVATE_SUBNET_IDS}"
require_non_blank "data private subnet ids" "${DATA_PRIVATE_SUBNET_IDS}"

echo "1/6 Verify the ECR repository exists"
aws ecr describe-repositories \
  --region "${AWS_REGION}" \
  --repository-names "${ECR_REPOSITORY_NAME}" \
  >/dev/null
echo "   OK: ${ECR_REPOSITORY_NAME}"

echo "2/6 Verify the S3 bucket exists and is writable"
tmpfile="$(mktemp)"
trap 'rm -f "${tmpfile}"' EXIT
printf 'supportdoc-task1-smoke\n' > "${tmpfile}"
smoke_key="deployment/task1-smoke-$(date +%s).txt"
aws s3api put-object \
  --region "${AWS_REGION}" \
  --bucket "${S3_BUCKET_NAME}" \
  --key "${smoke_key}" \
  --body "${tmpfile}" \
  >/dev/null
aws s3api head-object \
  --region "${AWS_REGION}" \
  --bucket "${S3_BUCKET_NAME}" \
  --key "${smoke_key}" \
  >/dev/null
aws s3api delete-object \
  --region "${AWS_REGION}" \
  --bucket "${S3_BUCKET_NAME}" \
  --key "${smoke_key}" \
  >/dev/null
echo "   OK: s3://${S3_BUCKET_NAME}/${smoke_key}"

echo "3/6 Verify subnet tiers and route tables"
python - "${AWS_REGION}" "${PUBLIC_SUBNET_IDS}" "${APP_PRIVATE_SUBNET_IDS}" "${DATA_PRIVATE_SUBNET_IDS}" "${PUBLIC_ROUTE_TABLE_ID}" "${APP_PRIVATE_ROUTE_TABLE_ID}" "${DATA_PRIVATE_ROUTE_TABLE_ID}" <<'PY'
from __future__ import annotations
import json
import subprocess
import sys

region, public_csv, app_csv, data_csv, public_rt, app_rt, data_rt = sys.argv[1:]
public_subnets = [item for item in public_csv.split(",") if item]
app_subnets = [item for item in app_csv.split(",") if item]
data_subnets = [item for item in data_csv.split(",") if item]

subnet_ids = public_subnets + app_subnets + data_subnets
subnets_payload = subprocess.check_output(
    ["aws", "ec2", "describe-subnets", "--region", region, "--subnet-ids", *subnet_ids],
    text=True,
)
subnets = {item["SubnetId"]: item for item in json.loads(subnets_payload)["Subnets"]}

for subnet_id in public_subnets:
    if not subnets[subnet_id]["MapPublicIpOnLaunch"]:
        raise SystemExit(f"Public subnet {subnet_id} does not map public IPs on launch.")
for subnet_id in app_subnets + data_subnets:
    if subnets[subnet_id]["MapPublicIpOnLaunch"]:
        raise SystemExit(f"Private subnet {subnet_id} unexpectedly maps public IPs on launch.")

route_tables_payload = subprocess.check_output(
    ["aws", "ec2", "describe-route-tables", "--region", region, "--route-table-ids", public_rt, app_rt, data_rt],
    text=True,
)
route_tables = {item["RouteTableId"]: item for item in json.loads(route_tables_payload)["RouteTables"]}

def default_targets(route_table: dict) -> list[str]:
    targets: list[str] = []
    for route in route_table.get("Routes", []):
        if route.get("DestinationCidrBlock") != "0.0.0.0/0":
            continue
        if route.get("GatewayId"):
            targets.append(route["GatewayId"])
        if route.get("NatGatewayId"):
            targets.append(route["NatGatewayId"])
    return targets

public_targets = default_targets(route_tables[public_rt])
if not any(target.startswith("igw-") for target in public_targets):
    raise SystemExit("Public route table is missing a default route to an internet gateway.")

app_targets = default_targets(route_tables[app_rt])
if not any(target.startswith("nat-") for target in app_targets):
    raise SystemExit("App private route table is missing a default route to a NAT gateway.")

data_targets = default_targets(route_tables[data_rt])
if any(target.startswith("igw-") for target in data_targets):
    raise SystemExit("Data private route table must not have a default route to an internet gateway.")

print("   OK: subnet map_public_ip flags and route-table targets match the intended split")
PY

echo "4/6 Verify security groups are not publicly exposed and follow ALB -> ECS -> RDS/inference"
python - "${AWS_REGION}" "${ALB_SECURITY_GROUP_ID}" "${ECS_SECURITY_GROUP_ID}" "${RDS_SECURITY_GROUP_ID}" "${INFERENCE_SECURITY_GROUP_ID}" <<'PY'
from __future__ import annotations
import json
import subprocess
import sys

region, alb_sg, ecs_sg, rds_sg, inference_sg = sys.argv[1:]
payload = subprocess.check_output(
    ["aws", "ec2", "describe-security-groups", "--region", region, "--group-ids", alb_sg, ecs_sg, rds_sg, inference_sg],
    text=True,
)
groups = {item["GroupId"]: item for item in json.loads(payload)["SecurityGroups"]}

def any_public_ingress(group: dict) -> bool:
    for permission in group.get("IpPermissions", []):
        for entry in permission.get("IpRanges", []):
            if entry.get("CidrIp") == "0.0.0.0/0":
                return True
        for entry in permission.get("Ipv6Ranges", []):
            if entry.get("CidrIpv6") == "::/0":
                return True
    return False

if not any_public_ingress(groups[alb_sg]):
    raise SystemExit("ALB security group is expected to be publicly reachable on the listener ports.")
if any_public_ingress(groups[ecs_sg]):
    raise SystemExit("ECS security group must not allow public ingress.")
if any_public_ingress(groups[rds_sg]):
    raise SystemExit("RDS security group must not allow public ingress.")
if any_public_ingress(groups[inference_sg]):
    raise SystemExit("Inference security group must not allow public ingress.")

def allows_from(group: dict, expected_source_sg: str, expected_port: int) -> bool:
    for permission in group.get("IpPermissions", []):
        if permission.get("IpProtocol") != "tcp":
            continue
        if permission.get("FromPort") != expected_port or permission.get("ToPort") != expected_port:
            continue
        for pair in permission.get("UserIdGroupPairs", []):
            if pair.get("GroupId") == expected_source_sg:
                return True
    return False

if not allows_from(groups[ecs_sg], alb_sg, 9001):
    raise SystemExit("ECS security group must allow port 9001 from the ALB security group.")
if not allows_from(groups[rds_sg], ecs_sg, 5432):
    raise SystemExit("RDS security group must allow port 5432 from the ECS security group.")
if not allows_from(groups[inference_sg], ecs_sg, 8000):
    raise SystemExit("Inference security group must allow port 8000 from the ECS security group.")

print("   OK: exposure and source-security-group rules match the intended flow")
PY

echo "5/6 Verify the backend API domain resolves"
python - "${BACKEND_API_DOMAIN}" <<'PY'
from __future__ import annotations
import socket
import sys
domain = sys.argv[1]
answers = sorted({item[4][0] for item in socket.getaddrinfo(domain, 443, proto=socket.IPPROTO_TCP)})
if not answers:
    raise SystemExit(f"No DNS answers returned for {domain}")
print("   OK: DNS answers -> " + ", ".join(answers))
PY

echo "6/6 Verify HTTPS responds at the backend API domain"
http_code="$(curl -sS -o /dev/null -w '%{http_code}' "https://${BACKEND_API_DOMAIN}/" --max-time 20)"
case "${http_code}" in
  200|301|302|401|403|404|503)
    echo "   OK: HTTPS responded with status ${http_code}"
    ;;
  *)
    echo "Unexpected HTTPS status code from https://${BACKEND_API_DOMAIN}/: ${http_code}" >&2
    exit 1
    ;;
esac

echo ""
echo "Task 1 verification passed."
