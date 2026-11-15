FROM node:24-alpine@sha256:116b800c3754b440ee0aa3ed2f20f5bf3d99a554bfd9adeea09ea8017f6e85f5 AS build
WORKDIR /app
COPY package.json package-lock.json ./
RUN --mount=type=cache,id=idea-board-npm,target=/root/.npm,sharing=locked \
    npm ci --prefer-offline --no-audit --no-fund
COPY tsconfig.json vite.config.ts index.html ./
COPY src ./src
RUN npm run build

FROM nginxinc/nginx-unprivileged:stable-alpine@sha256:f5116ed4606f3eb015dd4a8e28cb9b351476dc0ad4bc6e9f93b19cec130cdf03
ENV BACKEND_UPSTREAM=backend:8000 \
    NGINX_ENTRYPOINT_LOCAL_RESOLVERS=1 \
    NGINX_ENVSUBST_FILTER="BACKEND_UPSTREAM|NGINX_LOCAL_RESOLVERS"
COPY --link nginx.conf /etc/nginx/templates/default.conf.template
COPY --link --from=build /app/dist /usr/share/nginx/html
EXPOSE 8080
