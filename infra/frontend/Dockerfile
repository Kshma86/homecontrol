ARG NGINX_BASE_IMAGE=nginx@sha256:0e52bd054126cdc040b1276c0af347aeb02a41b9cfe305d6094767ac30e97949
FROM node@sha256:8a32c8cf649a49915a66e81e7a609223c708d0adabf288ee3f4077d765542f85 AS build

WORKDIR /app

COPY package*.json /app/
COPY .npm-cache/ /opt/hc-npm-cache/
RUN npm ci --offline --ignore-scripts --no-audit --no-fund --cache /opt/hc-npm-cache

COPY . /app
RUN npm run test:mower && npm run test:ai && npm run test:backup && npm run build

FROM ${NGINX_BASE_IMAGE}

COPY nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=build /app/dist /usr/share/nginx/html

EXPOSE 3000
HEALTHCHECK --interval=10s --timeout=3s --start-period=20s --retries=3 CMD ["wget", "-q", "-O", "/dev/null", "http://127.0.0.1:3000/index.html"]
