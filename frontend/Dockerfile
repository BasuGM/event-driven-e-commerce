FROM node:22-slim

WORKDIR /app

COPY package.json package-lock.json ./
# Stamp the lockfile hash so dev.sh skips reinstalling into a freshly created volume
RUN npm ci && sha1sum package-lock.json | cut -d' ' -f1 > node_modules/.lock-hash

COPY . .

ENV NEXT_TELEMETRY_DISABLED=1
EXPOSE 3000
CMD ["npm", "run", "dev"]
