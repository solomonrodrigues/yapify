# Yapify Backend

## Mobile App Update Policy

We will not use API versioning.  
Instead, the API will enforce a **minimum supported app version**.

- Clients send their version in a header (e.g. `X-App-Version: 2.3.0`) or with the auth/config request.  
- The server checks this against the minimum supported version.  
- If the client is outdated, the response includes:  

```json
{
  "update_required": true,
  "minimum_version": "2.5.0",
  "store_url": "https://apps.apple.com/app/..."
}
