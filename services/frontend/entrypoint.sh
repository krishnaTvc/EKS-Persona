#!/bin/sh
set -eu
# The first nameserver is Docker's DNS locally and CoreDNS in EKS.
NGINX_RESOLVER="$(awk '/^nameserver / {print $2; exit}' /etc/resolv.conf)"
: "${NGINX_RESOLVER:?No DNS nameserver was found}"
export NGINX_RESOLVER
# Replace only this variable; preserve Nginx's $host, $uri and proxy variables.
envsubst '${NGINX_RESOLVER}' < /etc/nginx/nginx.conf.template > /tmp/nginx.conf
exec nginx -c /tmp/nginx.conf -g 'daemon off;'
