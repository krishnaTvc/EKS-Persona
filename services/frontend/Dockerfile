FROM nginx:1.28-alpine
COPY nginx.conf /etc/nginx/nginx.conf.template
COPY entrypoint.sh /app-entrypoint.sh
COPY static/ /usr/share/nginx/html/
USER nginx
EXPOSE 8080
ENTRYPOINT ["/bin/sh", "/app-entrypoint.sh"]
