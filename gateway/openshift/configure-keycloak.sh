#!/usr/bin/env bash
# configure-keycloak.sh -- Idempotent Keycloak realm/client/user configuration
# for the MCP Gateway auth pipeline.
#
# This script is designed to be re-runnable: if the Keycloak pod restarts and
# loses its ephemeral PostgreSQL data, re-running this script reconstructs
# the realm, both clients (mcp-gateway, sdg-pipeline), the mcp-agent user, and
# both k8s Secrets.
#
# Manages two clients because they serve different grant types:
#   - mcp-gateway: Resource-Owner-Password-Credentials (grant via mcp-agent user)
#   - sdg-pipeline: pure client_credentials (service account, no user)
#
# Usage: bash configure-keycloak.sh [NAMESPACE] [KEYCLOAK_CR_NAME]
#   NAMESPACE       - Kubernetes namespace (default: otel25-gateway)
#   KEYCLOAK_CR_NAME - Name of the Keycloak CR (default: mcp-keycloak)

set -euo pipefail

NAMESPACE="${1:-otel25-gateway}"
KEYCLOAK_CR="${2:-mcp-keycloak}"

echo "=== Configuring Keycloak for MCP Gateway ==="
echo "Namespace: $NAMESPACE"
echo "Keycloak CR: $KEYCLOAK_CR"
echo ""

# --- Step 1: Extract admin credentials ---
echo "[1/10] Extracting admin credentials..."
ADMIN_SECRET="${KEYCLOAK_CR}-initial-admin"
ADMIN_USER=$(oc get secret "$ADMIN_SECRET" -n "$NAMESPACE" -o jsonpath='{.data.username}' | base64 -d)
ADMIN_PASS=$(oc get secret "$ADMIN_SECRET" -n "$NAMESPACE" -o jsonpath='{.data.password}' | base64 -d)
echo "  Admin user: $ADMIN_USER"

# --- Step 2: Get Keycloak route hostname ---
echo "[2/10] Getting Keycloak route hostname..."
KEYCLOAK_HOST=$(oc get route -n "$NAMESPACE" -l app=keycloak -o jsonpath='{.items[0].spec.host}' 2>/dev/null)
if [ -z "$KEYCLOAK_HOST" ]; then
  # Fall back to looking by name pattern
  KEYCLOAK_HOST=$(oc get route -n "$NAMESPACE" -o jsonpath='{.items[0].spec.host}')
fi
KEYCLOAK_URL="https://${KEYCLOAK_HOST}"
echo "  Keycloak URL: $KEYCLOAK_URL"

# --- Step 3: Obtain admin access token ---
echo "[3/10] Obtaining admin access token..."
TOKEN_RESPONSE=$(curl -sk -X POST "${KEYCLOAK_URL}/realms/master/protocol/openid-connect/token" \
  -d "grant_type=password" \
  -d "client_id=admin-cli" \
  -d "username=${ADMIN_USER}" \
  -d "password=${ADMIN_PASS}")

ADMIN_TOKEN=$(echo "$TOKEN_RESPONSE" | python3 -c "import sys,json; print(json.load(sys.stdin).get('access_token',''))" 2>/dev/null || true)
if [ -z "$ADMIN_TOKEN" ]; then
  echo "  ERROR: Failed to obtain admin token. Response: $TOKEN_RESPONSE"
  exit 1
fi
echo "  Admin token obtained (${#ADMIN_TOKEN} chars)"

# --- Step 4: Create realm "mcp" (skip if exists) ---
echo "[4/10] Creating realm 'mcp'..."
REALM_CHECK=$(curl -sk -o /dev/null -w "%{http_code}" \
  -H "Authorization: Bearer $ADMIN_TOKEN" \
  "${KEYCLOAK_URL}/admin/realms/mcp")

if [ "$REALM_CHECK" = "200" ]; then
  echo "  Realm 'mcp' already exists -- ensuring accessTokenLifespan is current."
  # Widened from the original 300s: Langflow's internal MCP session cache was
  # observed holding a token past its 300s expiry (reusing it ~3 minutes after
  # expiry on a DELETE /mcp session-teardown call), causing spurious 401s even
  # with a working 2-minute refresh CronJob. 1800s gives a large safety margin
  # over whatever staleness window that cache introduces.
  curl -sk -X PUT "${KEYCLOAK_URL}/admin/realms/mcp" \
    -H "Authorization: Bearer $ADMIN_TOKEN" \
    -H "Content-Type: application/json" \
    -d '{"accessTokenLifespan": 1800}' > /dev/null
else
  curl -sk -X POST "${KEYCLOAK_URL}/admin/realms" \
    -H "Authorization: Bearer $ADMIN_TOKEN" \
    -H "Content-Type: application/json" \
    -d '{
      "realm": "mcp",
      "enabled": true,
      "accessTokenLifespan": 1800
    }'
  echo "  Realm 'mcp' created."
fi

# --- Step 5: Create client "mcp-gateway" (skip if exists) ---
echo "[5/10] Creating client 'mcp-gateway'..."
EXISTING_CLIENTS=$(curl -sk \
  -H "Authorization: Bearer $ADMIN_TOKEN" \
  "${KEYCLOAK_URL}/admin/realms/mcp/clients?clientId=mcp-gateway")

CLIENT_COUNT=$(echo "$EXISTING_CLIENTS" | python3 -c "import sys,json; print(len(json.load(sys.stdin)))" 2>/dev/null || echo "0")

if [ "$CLIENT_COUNT" != "0" ]; then
  echo "  Client 'mcp-gateway' already exists, skipping creation."
  CLIENT_UUID=$(echo "$EXISTING_CLIENTS" | python3 -c "import sys,json; print(json.load(sys.stdin)[0]['id'])")
else
  CREATE_RESPONSE=$(curl -sk -X POST "${KEYCLOAK_URL}/admin/realms/mcp/clients" \
    -H "Authorization: Bearer $ADMIN_TOKEN" \
    -H "Content-Type: application/json" \
    -d '{
      "clientId": "mcp-gateway",
      "enabled": true,
      "clientAuthenticatorType": "client-secret",
      "serviceAccountsEnabled": false,
      "publicClient": false,
      "directAccessGrantsEnabled": true,
      "standardFlowEnabled": false,
      "protocol": "openid-connect"
    }' -w "\n%{http_code}" 2>&1)

  HTTP_CODE=$(echo "$CREATE_RESPONSE" | tail -1)
  if [ "$HTTP_CODE" != "201" ] && [ "$HTTP_CODE" != "409" ]; then
    echo "  WARNING: Client creation returned HTTP $HTTP_CODE"
  fi

  # Fetch the created client UUID
  EXISTING_CLIENTS=$(curl -sk \
    -H "Authorization: Bearer $ADMIN_TOKEN" \
    "${KEYCLOAK_URL}/admin/realms/mcp/clients?clientId=mcp-gateway")
  CLIENT_UUID=$(echo "$EXISTING_CLIENTS" | python3 -c "import sys,json; print(json.load(sys.stdin)[0]['id'])")
  echo "  Client 'mcp-gateway' created (UUID: $CLIENT_UUID)."
fi

# --- Step 6: Retrieve client secret ---
echo "[6/10] Retrieving client secret..."
SECRET_RESPONSE=$(curl -sk \
  -H "Authorization: Bearer $ADMIN_TOKEN" \
  "${KEYCLOAK_URL}/admin/realms/mcp/clients/${CLIENT_UUID}/client-secret")

CLIENT_SECRET=$(echo "$SECRET_RESPONSE" | python3 -c "import sys,json; print(json.load(sys.stdin).get('value',''))" 2>/dev/null || true)
if [ -z "$CLIENT_SECRET" ]; then
  # Generate a new secret
  curl -sk -X POST \
    -H "Authorization: Bearer $ADMIN_TOKEN" \
    "${KEYCLOAK_URL}/admin/realms/mcp/clients/${CLIENT_UUID}/client-secret" > /dev/null
  SECRET_RESPONSE=$(curl -sk \
    -H "Authorization: Bearer $ADMIN_TOKEN" \
    "${KEYCLOAK_URL}/admin/realms/mcp/clients/${CLIENT_UUID}/client-secret")
  CLIENT_SECRET=$(echo "$SECRET_RESPONSE" | python3 -c "import sys,json; print(json.load(sys.stdin).get('value',''))")
fi
echo "  Client secret retrieved (${#CLIENT_SECRET} chars)"

# --- Step 7: Create test user "mcp-agent" (skip if exists) ---
echo "[7/10] Creating test user 'mcp-agent'..."

EXISTING_USERS=$(curl -sk \
  -H "Authorization: Bearer $ADMIN_TOKEN" \
  "${KEYCLOAK_URL}/admin/realms/mcp/users?username=mcp-agent&exact=true")

USER_COUNT=$(echo "$EXISTING_USERS" | python3 -c "import sys,json; print(len(json.load(sys.stdin)))" 2>/dev/null || echo "0")

if [ "$USER_COUNT" != "0" ]; then
  echo "  User 'mcp-agent' already exists, skipping creation."
  USER_UUID=$(echo "$EXISTING_USERS" | python3 -c "import sys,json; print(json.load(sys.stdin)[0]['id'])")
  # Reuse the password already stored in the k8s Secret (if present) so re-running
  # this script against an existing user doesn't silently invalidate a password
  # other tooling may already be using.
  USER_PASSWORD=$(oc get secret keycloak-client-secret-mcp-gateway -n "$NAMESPACE" -o jsonpath='{.data.USER_PASSWORD}' 2>/dev/null | base64 -d || true)
  if [ -z "$USER_PASSWORD" ]; then
    USER_PASSWORD=$(openssl rand -hex 18)
    echo "  No existing USER_PASSWORD found in Secret -- generated a new one and will reset the user's credential."
    curl -sk -X PUT "${KEYCLOAK_URL}/admin/realms/mcp/users/${USER_UUID}/reset-password" \
      -H "Authorization: Bearer $ADMIN_TOKEN" \
      -H "Content-Type: application/json" \
      -d "{\"type\": \"password\", \"value\": \"${USER_PASSWORD}\", \"temporary\": false}" > /dev/null
  fi
else
  USER_PASSWORD=$(openssl rand -hex 18)
  # Keycloak 26+ requires email, firstName, lastName via User Profile
  curl -sk -X POST "${KEYCLOAK_URL}/admin/realms/mcp/users" \
    -H "Authorization: Bearer $ADMIN_TOKEN" \
    -H "Content-Type: application/json" \
    -d "{
      \"username\": \"mcp-agent\",
      \"email\": \"mcp-agent@otel25.local\",
      \"firstName\": \"MCP\",
      \"lastName\": \"Agent\",
      \"enabled\": true,
      \"emailVerified\": true,
      \"requiredActions\": [],
      \"credentials\": [{
        \"type\": \"password\",
        \"value\": \"${USER_PASSWORD}\",
        \"temporary\": false
      }]
    }"
  # Fetch user UUID
  EXISTING_USERS=$(curl -sk \
    -H "Authorization: Bearer $ADMIN_TOKEN" \
    "${KEYCLOAK_URL}/admin/realms/mcp/users?username=mcp-agent&exact=true")
  USER_UUID=$(echo "$EXISTING_USERS" | python3 -c "import sys,json; print(json.load(sys.stdin)[0]['id'])")
  echo "  User 'mcp-agent' created (UUID: $USER_UUID)."
fi

# Ensure user profile is complete and required actions are cleared
# (Keycloak 26+ User Profile requires email, firstName, lastName)
curl -sk -X PUT "${KEYCLOAK_URL}/admin/realms/mcp/users/${USER_UUID}" \
  -H "Authorization: Bearer $ADMIN_TOKEN" \
  -H "Content-Type: application/json" \
  -d "{
    \"email\": \"mcp-agent@otel25.local\",
    \"firstName\": \"MCP\",
    \"lastName\": \"Agent\",
    \"emailVerified\": true,
    \"requiredActions\": []
  }" > /dev/null
echo "  User profile completed and required actions cleared for 'mcp-agent'."

# --- Step 8: Create client "sdg-pipeline" (skip if exists) ---
echo "[8/10] Creating client 'sdg-pipeline'..."
EXISTING_SDG_CLIENTS=$(curl -sk \
  -H "Authorization: Bearer $ADMIN_TOKEN" \
  "${KEYCLOAK_URL}/admin/realms/mcp/clients?clientId=sdg-pipeline")

SDG_CLIENT_COUNT=$(echo "$EXISTING_SDG_CLIENTS" | python3 -c "import sys,json; print(len(json.load(sys.stdin)))" 2>/dev/null || echo "0")

if [ "$SDG_CLIENT_COUNT" != "0" ]; then
  echo "  Client 'sdg-pipeline' already exists, skipping creation."
  SDG_CLIENT_UUID=$(echo "$EXISTING_SDG_CLIENTS" | python3 -c "import sys,json; print(json.load(sys.stdin)[0]['id'])")
else
  # Pure client_credentials grant (service account, no user) -- diverges from
  # mcp-gateway's ROPC pattern intentionally, since the sdg pipeline scripts
  # (materialize_seeds.py's acquire_jwt) assume a true OAuth2 client_credentials flow.
  CREATE_SDG_RESPONSE=$(curl -sk -X POST "${KEYCLOAK_URL}/admin/realms/mcp/clients" \
    -H "Authorization: Bearer $ADMIN_TOKEN" \
    -H "Content-Type: application/json" \
    -d '{
      "clientId": "sdg-pipeline",
      "enabled": true,
      "clientAuthenticatorType": "client-secret",
      "serviceAccountsEnabled": true,
      "publicClient": false,
      "directAccessGrantsEnabled": false,
      "standardFlowEnabled": false,
      "protocol": "openid-connect"
    }' -w "\n%{http_code}" 2>&1)

  SDG_HTTP_CODE=$(echo "$CREATE_SDG_RESPONSE" | tail -1)
  if [ "$SDG_HTTP_CODE" != "201" ] && [ "$SDG_HTTP_CODE" != "409" ]; then
    echo "  WARNING: Client creation returned HTTP $SDG_HTTP_CODE"
  fi

  EXISTING_SDG_CLIENTS=$(curl -sk \
    -H "Authorization: Bearer $ADMIN_TOKEN" \
    "${KEYCLOAK_URL}/admin/realms/mcp/clients?clientId=sdg-pipeline")
  SDG_CLIENT_UUID=$(echo "$EXISTING_SDG_CLIENTS" | python3 -c "import sys,json; print(json.load(sys.stdin)[0]['id'])")
  echo "  Client 'sdg-pipeline' created (UUID: $SDG_CLIENT_UUID)."
fi

# --- Step 9: Retrieve sdg-pipeline client secret ---
echo "[9/10] Retrieving 'sdg-pipeline' client secret..."
SDG_SECRET_RESPONSE=$(curl -sk \
  -H "Authorization: Bearer $ADMIN_TOKEN" \
  "${KEYCLOAK_URL}/admin/realms/mcp/clients/${SDG_CLIENT_UUID}/client-secret")

SDG_CLIENT_SECRET=$(echo "$SDG_SECRET_RESPONSE" | python3 -c "import sys,json; print(json.load(sys.stdin).get('value',''))" 2>/dev/null || true)
if [ -z "$SDG_CLIENT_SECRET" ]; then
  curl -sk -X POST \
    -H "Authorization: Bearer $ADMIN_TOKEN" \
    "${KEYCLOAK_URL}/admin/realms/mcp/clients/${SDG_CLIENT_UUID}/client-secret" > /dev/null
  SDG_SECRET_RESPONSE=$(curl -sk \
    -H "Authorization: Bearer $ADMIN_TOKEN" \
    "${KEYCLOAK_URL}/admin/realms/mcp/clients/${SDG_CLIENT_UUID}/client-secret")
  SDG_CLIENT_SECRET=$(echo "$SDG_SECRET_RESPONSE" | python3 -c "import sys,json; print(json.load(sys.stdin).get('value',''))")
fi
echo "  Client secret retrieved (${#SDG_CLIENT_SECRET} chars)"

# --- Step 10: Create/update k8s Secrets ---
echo "[10/10] Creating/updating k8s Secrets..."
echo "  keycloak-client-secret-mcp-gateway..."
oc create secret generic keycloak-client-secret-mcp-gateway \
  -n "$NAMESPACE" \
  --from-literal=CLIENT_SECRET="$CLIENT_SECRET" \
  --from-literal=USER_PASSWORD="$USER_PASSWORD" \
  --dry-run=client -o yaml | oc apply -f - 2>&1

echo "  keycloak-client-secret-sdg-pipeline..."
oc create secret generic keycloak-client-secret-sdg-pipeline \
  -n "$NAMESPACE" \
  --from-literal=CLIENT_SECRET="$SDG_CLIENT_SECRET" \
  --dry-run=client -o yaml | oc apply -f - 2>&1

echo ""
echo "=== Verifying token endpoints ==="
TOKEN_TEST=$(curl -sk -X POST "${KEYCLOAK_URL}/realms/mcp/protocol/openid-connect/token" \
  -d "grant_type=password" \
  -d "client_id=mcp-gateway" \
  -d "client_secret=${CLIENT_SECRET}" \
  -d "username=mcp-agent" \
  -d "password=${USER_PASSWORD}")

ACCESS_TOKEN=$(echo "$TOKEN_TEST" | python3 -c "import sys,json; print(json.load(sys.stdin).get('access_token',''))" 2>/dev/null || true)

SDG_TOKEN_TEST=$(curl -sk -X POST "${KEYCLOAK_URL}/realms/mcp/protocol/openid-connect/token" \
  -d "grant_type=client_credentials" \
  -d "client_id=sdg-pipeline" \
  -d "client_secret=${SDG_CLIENT_SECRET}")

SDG_ACCESS_TOKEN=$(echo "$SDG_TOKEN_TEST" | python3 -c "import sys,json; print(json.load(sys.stdin).get('access_token',''))" 2>/dev/null || true)

echo ""
echo "=== Configuration Summary ==="
echo "  Keycloak URL:  $KEYCLOAK_URL"
echo "  Realm:         mcp"
echo "  Client:        mcp-gateway (ROPC via mcp-agent user)"
echo "  Client:        sdg-pipeline (client_credentials, service account)"
echo "  User:          mcp-agent"
echo "  K8s Secret:    keycloak-client-secret-mcp-gateway (namespace: $NAMESPACE)"
echo "  K8s Secret:    keycloak-client-secret-sdg-pipeline (namespace: $NAMESPACE)"

MCP_GATEWAY_OK=false
SDG_PIPELINE_OK=false
[ -n "$ACCESS_TOKEN" ] && [ "$ACCESS_TOKEN" != "" ] && MCP_GATEWAY_OK=true
[ -n "$SDG_ACCESS_TOKEN" ] && [ "$SDG_ACCESS_TOKEN" != "" ] && SDG_PIPELINE_OK=true

if [ "$MCP_GATEWAY_OK" = "true" ]; then
  echo "  Token test (mcp-gateway):  PASS (access_token received, ${#ACCESS_TOKEN} chars)"
else
  echo "  Token test (mcp-gateway):  FAIL"
  echo "    Response: $TOKEN_TEST"
fi

if [ "$SDG_PIPELINE_OK" = "true" ]; then
  echo "  Token test (sdg-pipeline): PASS (access_token received, ${#SDG_ACCESS_TOKEN} chars)"
else
  echo "  Token test (sdg-pipeline): FAIL"
  echo "    Response: $SDG_TOKEN_TEST"
fi

echo ""
if [ "$MCP_GATEWAY_OK" = "true" ] && [ "$SDG_PIPELINE_OK" = "true" ]; then
  echo "=== SUCCESS ==="
  exit 0
else
  echo "=== FAILED (one or more token retrievals failed) ==="
  exit 1
fi
