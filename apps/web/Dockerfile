FROM node:lts-alpine AS build

ENV NPM_CONFIG_UPDATE_NOTIFIER=false
ENV NPM_CONFIG_FUND=false

ARG PUBLIC_API_URL
ENV PUBLIC_API_URL=$PUBLIC_API_URL

WORKDIR /app

RUN npm install -g pnpm

COPY package.json pnpm-lock.yaml pnpm-workspace.yaml ./
RUN pnpm install --frozen-lockfile --ignore-scripts && pnpm rebuild esbuild

COPY . ./
RUN pnpm build && ls -la /app/build/

FROM node:lts-alpine AS runtime

WORKDIR /app

RUN npm install -g serve

COPY --from=build /app/build ./build

CMD ["serve", "build", "-l", "tcp://0.0.0.0:3000"]
