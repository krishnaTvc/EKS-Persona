#!/usr/bin/env python3
"""Run once in CloudShell, review and commit the resulting compatible add-on pins."""
import json
import os
from pathlib import Path
import re
import subprocess

region=os.environ.get('AWS_REGION','eu-north-1')
version='1.36'
names=['vpc-cni','kube-proxy','coredns','eks-pod-identity-agent','aws-ebs-csi-driver']
pins={}
for name in names:
    result=json.loads(subprocess.check_output([
        'aws','eks','describe-addon-versions','--region',region,
        '--addon-name',name,'--kubernetes-version',version,'--output','json'
    ]))
    versions=result['addons'][0]['addonVersions'] if result.get('addons') else []
    recommended=[entry for entry in versions if any(item.get('defaultVersion') for item in entry.get('compatibilities',[]))]
    candidates=recommended or versions
    if not candidates:
        raise SystemExit(f'No compatible {name} add-on found for EKS {version} in {region}')
    pins[name]=max(candidates,key=lambda item:tuple(map(int,re.findall(r'\d+',item['addonVersion']))))['addonVersion']
target=Path('terraform/infra/addons.auto.tfvars.json')
target.write_text(json.dumps({'addon_versions':pins},indent=2)+'\n')
print(target)
print(json.dumps(pins,indent=2))
