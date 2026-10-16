# Operations

## Infrastructure

### Hosting
- **App server:** Railway — pushes to `main` auto-deploy via GitHub integration
- **Database:** Railway-managed PostgreSQL
- **Worker:** Django Q2 (`python3 manage.py qcluster`) — must be started as a separate Railway service manually. Handles async notification processing and push delivery.

### Email
- **Sending:** Mailgun, via the `mail.yapify.net` subdomain. Outbound emails (verification, password reset) come from `donotreply@mail.yapify.net`. API key stored in Railway environment variables.
- **Receiving:** `support@yapify.net` is routed via Cloudflare Email Routing to `yapifyapp@gmail.com`. No mailbox on the server — support mail goes straight to Gmail.
- **DNS note:** Mailgun's SPF/DKIM/MX records sit on `mail.yapify.net`; Cloudflare's inbound MX records sit on `yapify.net`. They don't conflict.

---

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
```
