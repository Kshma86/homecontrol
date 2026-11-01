FROM node:20-alpine AS build

WORKDIR /app

COPY package*.json /app/
RUN npm ci

COPY . /app
RUN npm run test:mower && npm run test:ai && npm run test:backup && npm run build

FROM nginx:1.27-alpine

COPY nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=build /app/dist /usr/share/nginx/html

EXPOSE 3000
