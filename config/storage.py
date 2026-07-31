from urllib.parse import urlparse


def normalize_s3_endpoint(endpoint_url, media_location=""):
    """Return an SDK endpoint and object prefix safe for S3 URL signing."""
    endpoint_url = endpoint_url or None
    media_location = (media_location or "").strip("/")
    if not endpoint_url:
        return None, media_location

    parsed_endpoint = urlparse(endpoint_url)
    if (parsed_endpoint.hostname or "").lower().endswith(".amazonaws.com"):
        media_location = media_location or parsed_endpoint.path.strip("/")
        return None, media_location
    return endpoint_url, media_location
