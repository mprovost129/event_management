# ClamAV setup and operations

Gather HQs scans organization-document uploads synchronously before saving them.
The application uses ClamAV's `INSTREAM` protocol over a TCP connection to a
private `clamd` service. A clean response allows the upload; malware detection,
scanner outages, timeouts, and unexpected responses reject the upload without
saving it.

The repository does not currently provision ClamAV in `render.yaml`. Supply a
separate private service and validate it before accepting real document uploads.

## Production architecture

Use a Render **Private Service**, not a web service or background worker. Render
private services can receive private-network traffic without receiving a public
URL. Place ClamAV in the same Render workspace, environment, and region as the
Gather HQs web service.

Recommended service contract:

- Run an official, version-pinned `clamav/clamav` or `clamav/clamav-debian`
  image.
- Start `clamd` and FreshClam using the image's supported entrypoint.
- Listen for private TCP traffic on port `3310`.
- Never publish port `3310` to the internet. The application protocol does not
  add authentication or TLS around the private `clamd` connection.
- Ensure ClamAV's `StreamMaxLength` is greater than
  `DOCUMENT_UPLOAD_MAX_BYTES` (10 MiB by default).
- Keep virus signatures current. Monitor FreshClam logs and treat repeated
  update failures as an operational alert.
- Follow the official image guidance for `/var/lib/clamav`. A preloaded image
  avoids a full signature download on each fresh container; a persistent
  database directory can reduce repeated downloads when using a base image.

References:

- [Official ClamAV Docker guidance](https://docs.clamav.net/manual/Installing/Docker.html)
- [Render private services](https://render.com/docs/private-services)
- [Render private networking](https://render.com/docs/private-network)

## Render setup

1. In Render, create a Private Service from a reviewed, pinned official ClamAV
   image. Do not use an unpinned `latest` image for production.
2. Place it in the same region and environment as `gather-hqs-web`.
3. Confirm from the service logs that `clamd` is ready, FreshClam has a current
   signature database, and the service is listening on private port `3310`.
4. Open the service's **Connect** or **Internal** details and copy its internal
   hostname. Use only the hostname for `CLAMAV_HOST`, without `http://`,
   `https://`, or a port suffix.
5. Sync the Blueprint and provide `CLAMAV_HOST` when Render prompts for the
   `gather-hqs-runtime` environment group. The Blueprint shares this scanner
   contract with the web, worker, and scheduler so production checks use the
   same values:

   ```env
   DOCUMENT_UPLOAD_SCAN_BACKEND=clamav
   CLAMAV_HOST=the-private-service-hostname
   CLAMAV_PORT=3310
   CLAMAV_TIMEOUT_SECONDS=10
   ```

6. Save and deploy the services. The worker and scheduler do not currently scan
   uploads, but they inherit the values so production checks and future task
   execution use one deployment contract.
7. Run the connectivity and application checks below before setting
   `LEGAL_DRAFT=false` or accepting real uploads.

Do not set `DOCUMENT_UPLOAD_SCAN_BACKEND=disabled` in production as a recovery
shortcut. The deployment check rejects disabled scanning, and bypassing the
scanner would accept unexamined uploads.

## Connectivity check

From a Render Shell on a service in the same private network, send ClamAV's
`PING` command:

```text
python -c "import os,socket; s=socket.create_connection((os.environ['CLAMAV_HOST'], int(os.environ.get('CLAMAV_PORT', '3310'))), int(os.environ.get('CLAMAV_TIMEOUT_SECONDS', '10'))); s.sendall(b'zPING\0'); print(s.recv(64).rstrip(b'\0').decode()); s.close()"
```

The expected output is `PONG`. A successful TCP connection alone is not enough;
the protocol response confirms that the target is a responding `clamd` process.

Then run the production deployment check with the complete production
environment configured:

```text
python manage.py check --deploy --settings=config.Settings.prod
```

## Functional validation

Perform these checks in staging or with controlled test records:

1. Upload a small, ordinary PDF or text document. Confirm the upload succeeds
   and the stored document remains accessible only to an authorized role.
2. Download the standard EICAR anti-malware test file directly from the EICAR
   project and upload it. Do not commit or permanently store the test file in
   this repository. Confirm the form reports malware, no document record is
   created, and no object is retained in storage.
3. Stop or disconnect the ClamAV service and attempt another clean upload.
   Confirm the upload is rejected as temporarily unavailable and nothing is
   stored.
4. Restore ClamAV, wait for a successful `PONG`, and confirm clean uploads work
   again.
5. Review application, ClamAV, and FreshClam logs for the test interval. Logs
   must not contain uploaded document contents or credentials.

The automated protocol and fail-closed tests are:

```text
python -m pytest workspace/tests/test_file_scanning.py workspace/tests/test_workspace.py -q
```

## Monitoring and maintenance

- Alert when the private ClamAV service is unavailable or repeatedly restarts.
- Monitor FreshClam update success and signature age.
- Review application errors for repeated scanner-unavailable responses.
- Restart or upgrade ClamAV during a controlled window; document uploads will
  intentionally fail closed while it is unavailable.
- Test clean, EICAR, and unavailable-scanner behavior after image upgrades or
  network changes.
- Pin image upgrades, review ClamAV release notes, and retain a rollback image.

## Troubleshooting

| Symptom | Checks |
| --- | --- |
| Connection refused | Confirm `clamd` is ready and listening on port `3310`; verify the internal hostname and port. |
| Connection timeout | Confirm both services share a Render region/environment and private-network traffic is allowed. |
| Unexpected scanner response | Confirm the target is raw `clamd` TCP, not an HTTP proxy; inspect ClamAV logs. |
| Upload exceeds stream limit | Increase ClamAV `StreamMaxLength` above `DOCUMENT_UPLOAD_MAX_BYTES`, then restart and retest. |
| All uploads fail after deployment | Run the `PING` probe, confirm the four environment variables, and check ClamAV signature initialization. |
| Signatures repeatedly redownload | Review the official image/database-volume guidance and FreshClam logs. |

Record the selected image version, internal service name, last successful
signature update, clean-upload result, EICAR rejection, outage rejection, and
approver in the release evidence.
