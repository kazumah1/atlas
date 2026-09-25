FROM node:22.14-alpine AS build

ENV NPM_CONFIG_UPDATE_NOTIFIER=false
ENV NPM_CONFIG_FUND=false

WORKDIR /app

RUN corepack enable && corepack prepare pnpm@10.10.0 --activate

COPY package.json pnpm-lock.yaml pnpm-workspace.yaml ./
RUN pnpm install --frozen-lockfile --ignore-scripts && pnpm rebuild esbuild

COPY . ./
RUN pnpm build && ls -la /app/build/

FROM node:22.14-alpine AS runtime

WORKDIR /app

RUN npm install -g serve@14.2.4

COPY --from=build /app/build ./build

CMD ["serve", "build", "-l", "tcp://0.0.0.0:3000"]
