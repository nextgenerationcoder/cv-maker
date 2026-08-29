FROM nginx:1.27-alpine

COPY nginx.conf /etc/nginx/conf.d/default.conf
COPY index.html cv.html learning.html login.html signup.html forgot-password.html jobs.html job-detail.html settings.html \
     app.js cv.js learning.js auth.js jobs.js job-detail.js settings.js style.css \
     /usr/share/nginx/html/

EXPOSE 80
