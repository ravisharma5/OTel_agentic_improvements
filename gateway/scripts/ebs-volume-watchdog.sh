#!/usr/bin/env bash
# ebs-volume-watchdog.sh -- Self-heals the exact failure mode that caused a
# multi-hour outage on 2026-10-13: a node holding keycloak-postgres's PVC
# goes NotReady/dies, and the EBS volume is left genuinely stuck attached to
# that (dead) EC2 instance at the AWS API level (VolumeInUse), blocking the
# replacement pod from ever mounting it. Kubernetes cannot fix this itself --
# it requires an actual ec2:DetachVolume call, which this script makes using
# a minimally-scoped IAM user (ec2:Describe{Volumes,Instances,InstanceStatus},
# ec2:DetachVolume only -- see the IAM policy this CronJob's Secret was
# created from, no write/create/terminate permissions).
#
# Safety: only force-detaches when the EC2 instance currently holding the
# volume is NOT in "running" state (stopped/stopping/shutting-down/
# terminated) -- never rips a volume away from a genuinely healthy, running
# instance, even if Kubernetes briefly thinks the corresponding Node is
# NotReady (that could be a transient kubelet blip, not a dead node).
#
# Runs as a CronJob (ebs-volume-watchdog-cronjob.yaml) via the amazon/aws-cli
# image -- no custom image build needed, the aws-cli image already bundles
# bash, curl, and python3 (awscli itself is Python).

set -euo pipefail

NAMESPACE="${WATCHDOG_NAMESPACE:-otel25-gateway}"
K8S_API="https://kubernetes.default.svc"
TOKEN="$(cat /var/run/secrets/kubernetes.io/serviceaccount/token)"
CACERT="/var/run/secrets/kubernetes.io/serviceaccount/ca.crt"

echo "Checking for stuck FailedAttachVolume events in namespace ${NAMESPACE}..."

EVENTS_JSON=$(curl -sk --cacert "$CACERT" -H "Authorization: Bearer ${TOKEN}" \
  "${K8S_API}/api/v1/namespaces/${NAMESPACE}/events?fieldSelector=reason=FailedAttachVolume")

VOLUME_IDS=$(echo "$EVENTS_JSON" | python3 -c "
import json, re, sys
d = json.load(sys.stdin)
vols = set()
for item in d.get('items', []):
    msg = item.get('message', '')
    m = re.search(r'volume \"(vol-[0-9a-f]+)\"', msg)
    if m:
        vols.add(m.group(1))
print('\n'.join(vols))
")

if [ -z "$VOLUME_IDS" ]; then
  echo "No FailedAttachVolume events found. Nothing to do."
  exit 0
fi

for VOL_ID in $VOLUME_IDS; do
  echo "=== Checking ${VOL_ID} ==="
  ATTACHMENT=$(aws ec2 describe-volumes --volume-ids "$VOL_ID" \
    --query 'Volumes[0].Attachments[0]' --output json 2>&1)

  if [ "$ATTACHMENT" = "null" ] || [ -z "$ATTACHMENT" ]; then
    echo "  Volume ${VOL_ID} is not currently attached anywhere. Nothing to do."
    continue
  fi

  INSTANCE_ID=$(echo "$ATTACHMENT" | python3 -c "import json,sys; print(json.load(sys.stdin).get('InstanceId',''))")
  if [ -z "$INSTANCE_ID" ]; then
    echo "  Could not determine attached instance for ${VOL_ID}. Skipping."
    continue
  fi

  INSTANCE_STATE=$(aws ec2 describe-instance-status --instance-ids "$INSTANCE_ID" --include-all-instances \
    --query 'InstanceStatuses[0].InstanceState.Name' --output text 2>&1)
  echo "  ${VOL_ID} is attached to instance ${INSTANCE_ID}, state: ${INSTANCE_STATE}"

  if [ "$INSTANCE_STATE" = "running" ]; then
    echo "  Instance is running -- NOT detaching (would be unsafe). Leaving alone."
    continue
  fi

  echo "  Instance is not running (${INSTANCE_STATE}) -- force-detaching ${VOL_ID}..."
  aws ec2 detach-volume --volume-id "$VOL_ID" --force
  echo "  Detach requested. Kubernetes' own attach-detach-controller should retry the pending attach shortly."
done
