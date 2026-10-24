"""Optional scene check with a vision LLM (Gemini): does the closure photo still show the problem, and is it the
same place as the complaint photo? A lighter alternative to CLIP/DINOv2 (no torch, no 400 MB download).

PRIVACY: this sends the photo(s) to Google. It is OFF by default (AGENT_USE_VISION_LLM=1 to enable) and meant for the
labelled open-licence demo photos. Do not enable it on real citizen or officer photos without a data-sharing decision.
Output is labelled as an LLM judgement, never as a measurement.
"""
import base64
import io

import httpx
from PIL import Image
from pydantic import BaseModel, ValidationError

from . import config


class VisionReply(BaseModel):
    problem_still_visible: bool
    same_place_as_complaint: bool | None = None
    note: str = ""


def _jpeg_b64(img: Image.Image) -> str:
    img = img.convert("RGB")
    img.thumbnail((768, 768))
    buf = io.BytesIO()
    img.save(buf, "JPEG", quality=80)
    return base64.b64encode(buf.getvalue()).decode()


def judge(category: str, closure: Image.Image, complaint: Image.Image | None = None) -> VisionReply:
    parts = [{"text": (
        f"A municipal complaint about '{category}' was marked fixed. Image 1 is the officer's closure photo"
        + (", image 2 is the citizen's original complaint photo." if complaint else ".")
        + " Answer as JSON {problem_still_visible: bool, same_place_as_complaint: bool|null, note: short}. "
          "problem_still_visible is true if the closure photo still clearly shows the reported problem. "
          "same_place_as_complaint is null when there is no complaint photo; otherwise judge whether both photos "
          "show the same spot.")},
        {"inline_data": {"mime_type": "image/jpeg", "data": _jpeg_b64(closure)}}]
    if complaint is not None:
        parts.append({"inline_data": {"mime_type": "image/jpeg", "data": _jpeg_b64(complaint)}})
    r = httpx.post(
        f"https://generativelanguage.googleapis.com/v1beta/models/{config.GEMINI_MODEL}:generateContent",
        headers={"x-goog-api-key": config.GEMINI_API_KEY},
        json={"contents": [{"parts": parts}],
              "generationConfig": {"responseMimeType": "application/json", "temperature": 0}},
        timeout=max(config.LLM_TIMEOUT, 40))
    r.raise_for_status()
    try:
        return VisionReply.model_validate_json(r.json()["candidates"][0]["content"]["parts"][0]["text"])
    except (ValidationError, KeyError, ValueError) as exc:
        raise ValueError(f"vision reply unusable: {type(exc).__name__}")


def vision_checks(closure: Image.Image, category: str, complaint: Image.Image | None = None,
                  judge_fn=judge) -> tuple[list[str], list[str], dict]:
    """Same (flags, passed, details) vocabulary as clip_check: 'scene' and 'before_after'."""
    reply = judge_fn(category, closure, complaint)
    flags, passed = [], []
    (flags if reply.problem_still_visible else passed).append("scene")
    if reply.same_place_as_complaint is not None:
        (passed if reply.same_place_as_complaint else flags).append("before_after")
    return flags, passed, {"vision_llm": {"problem_still_visible": reply.problem_still_visible,
                                          "same_place_as_complaint": reply.same_place_as_complaint,
                                          "note": reply.note[:200], "judged_by": "LLM, not a measurement"}}
