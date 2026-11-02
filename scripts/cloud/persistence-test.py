#!/usr/bin/env python3
"""Use the public frontend URL; restarts only the MySQL StatefulSet."""
import json
import subprocess
import sys
from urllib.request import Request,urlopen

if len(sys.argv)!=2:
    raise SystemExit('Usage: python3 scripts/cloud/persistence-test.py http://YOUR_NLB_HOSTNAME')
base=sys.argv[1].rstrip('/')
request=Request(base+'/api/registrations',data=json.dumps({'name':'EBS Explorer','age':35}).encode(),headers={'Content-Type':'application/json'})
with urlopen(request,timeout=30) as response:
    before=json.load(response)
subprocess.run(['kubectl','-n','persona','rollout','restart','statefulset/mysql'],check=True)
subprocess.run(['kubectl','-n','persona','rollout','status','statefulset/mysql','--timeout=10m'],check=True)
with urlopen(base+'/api/registrations/'+before['registration_id'],timeout=30) as response:
    after=json.load(response)
assert after==before,'Saved record changed after MySQL pod recreation'
print('PASS: same registration and animal survived MySQL pod recreation on the EBS-backed PVC.')
