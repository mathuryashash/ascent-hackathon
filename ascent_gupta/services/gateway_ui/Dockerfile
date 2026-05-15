FROM node:20-slim

RUN useradd --system --uid 1004 --no-create-home uiuser

WORKDIR /app

COPY package.json .
RUN npm install --omit=dev

COPY src/ ./src/
COPY public/ ./public/
USER uiuser

EXPOSE 3000

CMD ["node", "src/server.js"]
