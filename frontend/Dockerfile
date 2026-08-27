FROM nginx:1.27-alpine

COPY nginx.conf /etc/nginx/conf.d/default.conf
COPY index.html cv.html app.js cv.js style.css /usr/share/nginx/html/

EXPOSE 80
