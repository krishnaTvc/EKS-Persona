FROM nginx:stable-alpine-slim

RUN apk upgrade --no-cache \
    && apk add --no-cache gettext-envsubst \
    && command -v envsubst \
    && nginx -t

COPY nginx.conf /etc/nginx/nginx.conf.template
COPY entrypoint.sh /app-entrypoint.sh
COPY static/ /usr/share/nginx/html/

USER nginx
EXPOSE 8080
ENTRYPOINT ["/bin/sh", "/app-entrypoint.sh"]
