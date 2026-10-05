#!/usr/bin/env python3
"""Check if virtualServers are in the gateway config secret."""
import json, base64, subprocess, sys

r = subprocess.run(
    ['oc', 'get', 'secret', 'mcp-gateway-config', '-n', 'otel25-gateway', '-o', 'json'],
    capture_output=True, text=True
)
d = json.loads(r.stdout)
decoded = base64.b64decode(d['data']['config.yaml']).decode('utf-8')

if 'virtualServers' in decoded:
    print('virtualServers present in config')
else:
    print('virtualServers MISSING from config')

print('---')
print(decoded)
