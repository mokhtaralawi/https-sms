"""httpSMS-compatible API layer.

Exposes a few endpoints matching the original httpSMS (https://httpsms.com)
public API so that existing clients such as the "mang_dept" application can
talk to this self-hosted gateway without modification.

The original httpSMS client authenticates with a plain `x-api-key` header and
uses routes like `/messages/send` and `/heartbeats?owner=<phone>`. We map these
onto our own message/device models.
"""
