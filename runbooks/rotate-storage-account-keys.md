---
title: Rotate storage account keys
service: platform
tags: [storage, secrets, rotation, keys]
---

# Rotate storage account keys

Quarterly, or at once if a key may have leaked.

## Steps

1. Move every consumer to the secondary key, or better, to a managed identity.
2. Regenerate the primary key.
3. Update the secret store entry and restart consumers.
4. Repeat for the secondary key.

## Do not paste keys in tickets

A ticket from last quarter contained a full connection string like this one:

```text
DefaultEndpointsProtocol=https;AccountName=stlogsprod01;AccountKey=ZmFrZS1rZXktZm9yLWRlbW8tb25seQ==
```

That value is a fake used to test redaction. Real keys belong only in the secret store.
Questions go to the platform on-call, platform-oncall@example.test.
