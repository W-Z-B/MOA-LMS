#!/usr/bin/env sh
# Prints two random values for .env: DJANGO_SECRET_KEY and FIELD_ENCRYPTION_KEY.
# Never paste these into version control.
echo "DJANGO_SECRET_KEY=$(python3 -c 'import secrets;print(secrets.token_urlsafe(50))' 2>/dev/null || py -c 'import secrets;print(secrets.token_urlsafe(50))')"
echo "FIELD_ENCRYPTION_KEY=$(python3 -c 'import secrets,base64;print(base64.urlsafe_b64encode(secrets.token_bytes(32)).decode())' 2>/dev/null || py -c 'import secrets,base64;print(base64.urlsafe_b64encode(secrets.token_bytes(32)).decode())')"
