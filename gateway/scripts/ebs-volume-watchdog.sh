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
# bash and curl. It does NOT expose a bare python3/jq on PATH (awscli's own
# Python is embedded, not general-purpose) -- confirmed live, so this script
# deliberately avoids both and relies on `aws ... --query/--output text`
# (JMESPath, built into the CLI) plus plain grep instead.

set -euo pipefail

NAMESPACE="${WATCHDOG_NAMESPACE:-otel25-gateway}"
K8S_API="https://kubernetes.default.svc"
TOKEN="$(cat /var/run/secrets/kubernetes.io/serviceaccount/token)"
CACERT="/var/run/secrets/kubernetes.io/serviceaccount/ca.crt"

echo "Checking for stuck FailedAttachVolume events in namespace ${NAMESPACE}..."

EVENTS_JSON=$(curl -sk --cacert "$CACERT" -H "Authorization: Bearer ${TOKEN}" \
  "${K8S_API}/api/v1/namespaces/${NAMESPACE}/events?fieldSelector=reason=FailedAttachVolume")

# Plain grep instead of a JSON parser (python3/jq aren't present in the
# amazon/aws-cli image) -- the volume-id format is distinctive enough that a
# full JSON parse isn't needed, just pulling the pattern out of the raw body.
# `|| true`: grep exits 1 on no-match, which is the common/expected case here
# (no stuck events) -- under `set -e -o pipefail` that would otherwise kill
# the whole script silently right at this line instead of reaching the
# explicit empty-check below.
VOLUME_IDS=$( (echo "$EVENTS_JSON" | grep -oE 'vol-[0-9a-f]+' | sort -u) || true )

if [ -z "$VOLUME_IDS" ]; then
  echo "No FailedAttachVolume events found. Nothing to do."
  exit 0
fi

for VOL_ID in $VOLUME_IDS; do
  echo "=== Checking ${VOL_ID} ==="

  # Kubernetes Events persist for ~1h after the underlying problem is already
  # resolved (e.g. the volume was already manually cleaned up, or a previous
  # watchdog run already fixed it) -- confirmed live: describe-volumes on an
  # already-deleted volume returns InvalidVolume.NotFound (exit 254), which
  # would otherwise kill the whole script here under set -e.
  if ! DESCRIBE_OUT=$(aws ec2 describe-volumes --volume-ids "$VOL_ID" --query 'Volumes[0].Attachments[0].InstanceId' --output text 2>&1); then
    if echo "$DESCRIBE_OUT" | grep -q "InvalidVolume.NotFound"; then
      echo "  Volume ${VOL_ID} no longer exists (already cleaned up). Nothing to do."
      continue
    fi
    echo "  Unexpected error describing ${VOL_ID}: ${DESCRIBE_OUT}"
    continue
  fi
  INSTANCE_ID="$DESCRIBE_OUT"

  if [ -z "$INSTANCE_ID" ] || [ "$INSTANCE_ID" = "None" ]; then
    echo "  Volume ${VOL_ID} is not currently attached anywhere. Nothing to do."
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
