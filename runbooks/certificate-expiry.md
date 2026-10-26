---
title: TLS certificate close to expiry
service: web
tags: [tls, certificate, expiry]
---

# TLS certificate close to expiry

## Triage

1. Check the expiry: `openssl s_client -connect api.example.test:443 -servername api.example.test </dev/null | openssl x509 -noout -enddate`.
2. Find out whether the certificate is managed (automatic renewal) or uploaded by hand.

## Renew

- Managed certificate: check why automatic renewal did not run, usually a DNS validation record.
- Uploaded certificate: request a new one, upload it to the secret store, then rotate the listener.

## Escalate

Open a sev3 ticket 14 days before expiry and a sev2 at 3 days.
