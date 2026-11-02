#!/usr/bin/env python3
"""Run once in CloudShell; copy each value into the matching GitHub Actions Secret."""
import secrets
for name in ['MYSQL_ROOT_PASSWORD','REGISTRATION_PASSWORD','PERSONA_PASSWORD']:
    print(f'{name}={secrets.token_hex(24)}')
