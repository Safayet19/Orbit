# syntax=docker/dockerfile:1.7

FROM node:22-alpine AS dependencies

WORKDIR /app
COPY package.json package-lock.json ./
RUN --mount=type=cache,target=/root/.npm npm ci

FROM dependencies AS development

ENV VITE_HOST=0.0.0.0
ENV VITE_USE_POLLING=true

COPY . .
EXPOSE 5173
CMD ["npm", "run", "dev", "--", "--host", "0.0.0.0", "--strictPort"]

FROM dependencies AS build

COPY . .
RUN npm run build
