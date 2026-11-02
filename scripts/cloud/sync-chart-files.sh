#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/../.."
cp database/init/01-schema.sql charts/persona/files/01-schema.sql
cp database/init/02-users.sh charts/persona/files/02-users.sh
