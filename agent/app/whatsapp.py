"""Module 3 (part): WhatsApp Cloud API channel. Shares the request table and reply parsing with Telegram;
only the transport differs. The free test number can message only pre-registered recipients, so contacts are
our own phones. Start this only after the Telegram round trip passes (Q11)."""
import httpx

from . import config


def send_text(wa_id: str, text: str) -> None:
    if not (config.WHATSAPP_TOKEN and config.WHATSAPP_PHONE_NUMBER_ID):
        raise RuntimeError("WHATSAPP_TOKEN / WHATSAPP_PHONE_NUMBER_ID not set")
    r = httpx.post(f"https://graph.facebook.com/v20.0/{config.WHATSAPP_PHONE_NUMBER_ID}/messages",
                   headers={"Authorization": f"Bearer {config.WHATSAPP_TOKEN}"},
                   json={"messaging_product": "whatsapp", "to": wa_id, "type": "text", "text": {"body": text}},
                   timeout=10)
    r.raise_for_status()


def parse_payload(payload: dict) -> list[dict]:
    """Return [{'wa_id', 'text', 'has_photo'}] for each inbound message in a Cloud API webhook payload."""
    out = []
    for entry in payload.get("entry", []):
        for change in entry.get("changes", []):
            for m in (change.get("value") or {}).get("messages", []):
                kind = m.get("type")
                text = (m.get("text") or {}).get("body") or (m.get("image") or {}).get("caption") or ""
                if kind == "interactive":
                    text = ((m["interactive"].get("button_reply") or m["interactive"].get("list_reply") or {})
                            .get("title", ""))
                out.append({"wa_id": m.get("from", ""), "text": text, "has_photo": kind == "image"})
    return out


def send_template(wa_id: str, name: str = "hello_world", lang: str = "en_US") -> None:
    """Open a conversation with a pre-approved template. Free text only works inside the 24 h window that starts
    when the user messages us, so the first business-initiated message must be a template (the test number comes
    with `hello_world`)."""
    if not (config.WHATSAPP_TOKEN and config.WHATSAPP_PHONE_NUMBER_ID):
        raise RuntimeError("WHATSAPP_TOKEN / WHATSAPP_PHONE_NUMBER_ID not set")
    r = httpx.post(f"https://graph.facebook.com/v20.0/{config.WHATSAPP_PHONE_NUMBER_ID}/messages",
                   headers={"Authorization": f"Bearer {config.WHATSAPP_TOKEN}"},
                   json={"messaging_product": "whatsapp", "to": wa_id, "type": "template",
                         "template": {"name": name, "language": {"code": lang}}}, timeout=10)
    r.raise_for_status()
