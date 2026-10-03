ARG NODE_IMAGE=node:22-alpine@sha256:0a7108bf6c7bf5de370ffb1a3ed6be93d405b43ff159f681a8d18c0e2bc2e402
ARG NGINX_IMAGE=nginx:stable-alpine@sha256:0985e772fb9f729e6fa0980da05fca5d9c468e870eed43071545afa9d2e27d94
FROM ${NODE_IMAGE} AS builder
WORKDIR /build
COPY package.json package-lock.json ./
RUN npm ci --ignore-scripts
COPY . .
RUN npm run build

FROM ${NGINX_IMAGE} AS runtime
COPY nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=builder --chown=nginx:nginx /build/dist /usr/share/nginx/html
RUN apk add --upgrade --no-cache libexpat=2.8.5-r0 pcre2=10.49-r0 \
    && chown -R nginx:nginx /var/cache/nginx /var/run /etc/nginx/conf.d
USER nginx
EXPOSE 8080 8443
HEALTHCHECK --interval=30s --timeout=3s --start-period=5s --retries=3 \
    CMD wget -q -O /dev/null http://127.0.0.1:8080/healthz || exit 1
CMD ["nginx", "-g", "daemon off;"]
