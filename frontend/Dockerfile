# Build the app
FROM node:24-alpine AS build

# microcanvas installs from GitHub, with git
RUN apk add --no-cache git

WORKDIR /app

# Install dependencies only, so this layer is cached until the lockfile changes
COPY package.json package-lock.json ./
RUN --mount=type=cache,target=/root/.npm npm ci

COPY . .
RUN npm run build

# Serve it
FROM nginx:stable-alpine

COPY nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=build /app/dist /usr/share/nginx/html
