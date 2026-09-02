# Image Redaction Agent

Uses Azure Document Intelligence OCR geometry and Azure AI Language PII detection to burn irreversible black masks into matching image pixels. It supports text-based PII in raster images; general object and face detection are outside its current scope.

Input uses an `image` object with synthetic or authorized `content_base64`, an `image/*` `content_type`, and a `filename`. The response contains a redacted PNG and privacy-safe entity metadata. Original content is never logged or persisted.
