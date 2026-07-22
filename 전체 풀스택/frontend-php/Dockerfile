FROM php:8.3-apache
RUN apt-get update && apt-get install -y --no-install-recommends libcurl4-openssl-dev \
    && docker-php-ext-install curl \
    && a2enmod rewrite headers setenvif \
    && rm -rf /var/lib/apt/lists/*
COPY apache/xconcep-auth.conf /etc/apache2/conf-available/xconcep-auth.conf
RUN a2enconf xconcep-auth
COPY public/ /var/www/html/
COPY src/ /var/www/src/
COPY entrypoint.sh /usr/local/bin/entrypoint.sh
RUN chmod +x /usr/local/bin/entrypoint.sh
ENTRYPOINT ["entrypoint.sh"]
CMD ["apache2-foreground"]
