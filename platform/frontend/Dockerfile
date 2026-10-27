FROM node:18-alpine AS build

WORKDIR /app

# Declare build argument for API URL
ARG VITE_APP_API_URL
ENV VITE_APP_API_URL=$VITE_APP_API_URL

# Copy package files
COPY package*.json ./

# Install dependencies with legacy-peer-deps to handle react-mathjax compatibility
RUN npm install --legacy-peer-deps

# Install additional UI and math dependencies and emotion for styling
RUN npm install --legacy-peer-deps @mui/material @mui/icons-material @emotion/react @emotion/styled

# Copy source code
COPY . .

# Build the application
RUN npm run build

# Production stage
FROM nginx:alpine

# Copy built files
COPY --from=build /app/dist /usr/share/nginx/html

# Copy nginx configuration
COPY nginx.conf /etc/nginx/conf.d/default.conf

EXPOSE 80

CMD ["nginx", "-g", "daemon off;"]