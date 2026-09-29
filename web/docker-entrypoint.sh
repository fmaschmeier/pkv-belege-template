#!/bin/sh
set -e

# Generate htpasswd file from environment variables
# Ohne eigene Zugangsdaten startet der Container nicht: kein Standardpasswort für Gesundheitsdaten.
if [ -z "$BASIC_AUTH_USER" ] || [ -z "$BASIC_AUTH_PASS" ] || [ "$BASIC_AUTH_PASS" = "changeme" ]; then
    echo "ERROR: BASIC_AUTH_USER and BASIC_AUTH_PASS must be set (and not 'changeme')" >&2
    exit 1
fi
echo "Generating .htpasswd for user: $BASIC_AUTH_USER"
htpasswd -cb /etc/nginx/.htpasswd "$BASIC_AUTH_USER" "$BASIC_AUTH_PASS"

# Start nginx
exec "$@"
