# Vendored Bootstrap 5.3.3

Served from our own origin rather than a public CDN so a third-party outage
cannot strip the styling from every subscriber site we host.

Files are byte-for-byte the official `bootstrap@5.3.3` npm release. Their SRI
hashes match the ones previously used against jsDelivr:

- `css/bootstrap.min.css` sha384-QWTKZyjpPEjISv5WaRU9OFeRpok6YctnYmDr5pNlyT2bRjXh0JMhjY6hW+ALEwIH
- `js/bootstrap.bundle.min.js` sha384-YvpcrYf0tY3lHB60NNkmXc5s9fDVZLESaAA55NDzOxhy9GkcIdslK1eN7N6jIeHz

## Upgrading

```bash
npm pack bootstrap@<version>
tar xzf bootstrap-<version>.tgz
cp package/dist/css/bootstrap.min.css* static/vendor/bootstrap-<version>/css/
cp package/dist/js/bootstrap.bundle.min.js* static/vendor/bootstrap-<version>/js/
```

Then update the two `{% static %}` paths in `templates/base.html` and delete the
old directory. WhiteNoise fingerprints these files at collectstatic time, so
cache busting is handled.
