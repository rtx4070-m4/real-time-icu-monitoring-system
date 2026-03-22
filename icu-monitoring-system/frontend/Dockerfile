FROM node:20-alpine AS builder

WORKDIR /app

COPY package.json package-lock.json* ./
RUN npm ci --silent

COPY . .

ENV REACT_APP_API_URL=http://localhost:8080
ENV REACT_APP_WS_URL=http://localhost:8080
ENV REACT_APP_AI_URL=http://localhost:8082

RUN npm run build

# ── Nginx serving ──────────────────────────────────────────────────────────────
FROM nginx:1.25-alpine

COPY --from=builder /app/build /usr/share/nginx/html

# React Router support (SPA)
RUN printf 'server {\n\
  listen 80;\n\
  root /usr/share/nginx/html;\n\
  index index.html;\n\
  location / {\n\
    try_files $uri $uri/ /index.html;\n\
  }\n\
  location /api {\n\
    proxy_pass http://backend-api:8080;\n\
    proxy_set_header Host $host;\n\
  }\n\
  location /ws {\n\
    proxy_pass http://backend-api:8080;\n\
    proxy_http_version 1.1;\n\
    proxy_set_header Upgrade $http_upgrade;\n\
    proxy_set_header Connection "upgrade";\n\
  }\n\
  gzip on;\n\
  gzip_types text/plain text/css application/json application/javascript;\n\
}\n' > /etc/nginx/conf.d/default.conf

EXPOSE 80

CMD ["nginx", "-g", "daemon off;"]
