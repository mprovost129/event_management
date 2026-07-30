# Cloudmersive malware scanning

Gather HQs uses Cloudmersive's Advanced Virus Scan API for production
organization-document uploads. The application sends each file to Cloudmersive
before saving it. Only an explicit `CleanResult: true` response permits storage;
a detection, policy rejection, timeout, quota/rate-limit response, authentication
failure, or unexpected response fails closed and leaves the upload unsaved.

ClamAV remains supported as a self-hosted alternative. Its operational guide is
in `CLAMAV_SETUP.md`.

## Render configuration

1. Create a Cloudmersive account and copy its API key from the Cloudmersive
   portal.
2. Sync the Render Blueprint. When prompted for `CLOUDMERSIVE_API_KEY`, paste
   the key as a secret. Do not commit it or put it in a public support message.
3. Confirm the shared `gather-hqs-runtime` environment group contains:

   ```text
   DOCUMENT_UPLOAD_SCAN_BACKEND=cloudmersive
   DOCUMENT_UPLOAD_MAX_BYTES=3500000
   CLOUDMERSIVE_API_URL=https://api.cloudmersive.com/virus/scan/file/advanced
   CLOUDMERSIVE_TIMEOUT_SECONDS=20
   ```

4. Redeploy the web service. The deploy checks reject a missing key, disabled
   scanning, a non-HTTPS API URL, or an invalid timeout.

The API key is attached to outbound requests in the `Apikey` header. Gather HQs
does not log the key, the uploaded file, or Cloudmersive's detailed scan result.
Rotate the key in Cloudmersive and Render if it may have been exposed.

## Free-tier operating limits

As of July 30, 2026, Cloudmersive lists its free evaluation tier as 600 API calls
per month, one call per second, one simultaneous request, and a 3.5 MB maximum
file size. The Render Blueprint therefore caps organization documents at
3,500,000 bytes. Verify the current limits in Cloudmersive's pricing and FAQ
before launch because provider terms can change.

Every upload attempt that reaches Cloudmersive consumes capacity. When the
monthly quota is exhausted or requests overlap beyond the provider's limit,
uploads fail closed and the user must try later. During the pilot:

- monitor Cloudmersive usage at least weekly and before upload-heavy events;
- avoid simultaneous test uploads;
- reserve quota for real uploads near month end; and
- move to a paid tier or the self-hosted ClamAV backend before increasing the
  upload limit or relying on high-volume document workflows.

## Scan policy

Gather HQs uses the advanced endpoint with content verification and restricts
clean results to the extensions in `DOCUMENT_UPLOAD_ALLOWED_EXTENSIONS`. It also
rejects executables, invalid or misleading files, scripts, encrypted/password-
protected files, macros, XML external entities, insecure deserialization, HTML,
unsafe archives, OLE embedded objects, and unwanted automatic actions.

This intentionally means a file can be rejected without containing a named
virus. A rejected document should be recreated in a simple supported format and
uploaded again; do not weaken the policy to admit one unknown file.

## Launch validation

Use a non-production organization and perform all of these checks:

1. Upload a small, known-clean PDF and confirm it is saved and downloadable by
   an authorized staff member.
2. Download the standard EICAR anti-malware test file directly from the EICAR
   website. Do not commit it. Confirm the upload is rejected and no document
   record or storage object is created.
3. Temporarily use an invalid API key, redeploy, and confirm uploads fail closed.
   Restore the real key immediately.
4. Temporarily set the API URL to an HTTPS endpoint that cannot answer, confirm
   the timeout fails closed, and restore the documented endpoint.
5. Try a file slightly larger than 3,500,000 bytes and confirm the form rejects
   it before an API call is made.
6. Review Cloudmersive usage to confirm the expected calls were counted.

Never test by disabling scanning in production.

## Privacy and vendor review

Organization documents are disclosed to Cloudmersive for security scanning
before storage. Before accepting real customer documents, record Cloudmersive in
the production subprocessor inventory and review its current terms, privacy
notice, security materials, data-processing terms, data locations, retention
claims, and incident-notification commitments. Obtain any agreement required by
your customers or applicable law. The public Privacy Notice discloses this
security-provider processing, but it is not a substitute for vendor diligence or
legal review.

## Troubleshooting

| Symptom | Response |
| --- | --- |
| Deploy check reports a missing key | Set `CLOUDMERSIVE_API_KEY` in the Render environment group and redeploy. |
| Every file is rejected | Confirm the file is genuine and supported, inspect Cloudmersive usage/status, then validate the key and endpoint. |
| Upload reports scanner unavailable | Check quota, rate/concurrency limits, provider status, outbound connectivity, and credentials. Retry only after the cause is understood. |
| Files over 3.5 MB fail | This is required by the free tier. Reduce the file or upgrade the provider plan before increasing `DOCUMENT_UPLOAD_MAX_BYTES`. |
| A safe Office file is rejected | Remove macros, embedded objects, passwords, scripts, or automatic actions and export a simple PDF. |

Do not include the API key or document contents in logs or support tickets.
