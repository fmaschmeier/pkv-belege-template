# Build stage
FROM node:20-alpine AS builder

WORKDIR /app

# Copy package files
COPY package*.json ./

# Install dependencies
RUN npm ci

# Copy source files
COPY . .

# Build arguments for Vite env vars (passed at build time)
ARG VITE_SUPABASE_URL
ARG VITE_SUPABASE_KEY
ARG VITE_API_URL
ARG VITE_INSURANCE_NUMBER
ARG VITE_RECIPIENT_EMAIL
ARG VITE_CC_EMAIL
ARG VITE_SENDER_NAME
ARG VITE_SENDER_EMAIL
ARG VITE_SENDER_MOBILE
ARG VITE_PERSON_NAMES

# Build the app
RUN npm run build

# Production stage
FROM nginx:alpine

# Install apache2-utils for htpasswd
RUN apk add --no-cache apache2-utils

# Copy nginx config
COPY nginx.conf /etc/nginx/conf.d/default.conf

# Copy entrypoint script
COPY docker-entrypoint.sh /docker-entrypoint.sh
RUN chmod +x /docker-entrypoint.sh

# Copy built files
COPY --from=builder /app/dist /usr/share/nginx/html

# Expose port 8080 (Cloud Run requirement)
EXPOSE 8080

# Basic Auth: BASIC_AUTH_USER und BASIC_AUTH_PASS zur Laufzeit setzen (z. B. Cloud Run, Secret Manager).
# Bewusst ohne Standardwerte – ohne sie startet der Container nicht (siehe docker-entrypoint.sh).

ENTRYPOINT ["/docker-entrypoint.sh"]
CMD ["nginx", "-g", "daemon off;"]
