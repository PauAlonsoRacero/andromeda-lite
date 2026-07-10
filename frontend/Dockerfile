# ── Etapa 1: Build con Node ───────────────────────────────────────────────────
FROM node:20-alpine AS builder

WORKDIR /app

# Copiar package.json primero — cachea esta capa si no cambian las dependencias
COPY package*.json ./
RUN npm install

# Copiar el resto del código y compilar
COPY . .
# Cache-buster: invalida la caché de esta capa en cada build para evitar
# servir frontend viejo. El valor cambia con cada reconstrucción.
ARG CACHE_BUST=unknown
RUN echo "build: $CACHE_BUST" && npm run build
# Resultado en /app/dist

# ── Etapa 2: Servir con nginx ─────────────────────────────────────────────────
FROM nginx:alpine

# Copiar los archivos compilados
COPY --from=builder /app/dist /usr/share/nginx/html

# Copiar la configuración de nginx (proxy + SSE + SPA fallback)
COPY nginx.conf /etc/nginx/conf.d/default.conf

EXPOSE 80

# nginx arranca automáticamente con el CMD por defecto de la imagen
