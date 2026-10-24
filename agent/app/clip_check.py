"""Module 1 (part): CLIP ViT-B/32 checks on the closure photo. Torch and open_clip are imported lazily so the
service starts without them; the embedder is injectable so tests never download the model.

  scene presence : zero-shot, "a photo of <problem>" vs "a photo of <fixed state>" per category
  before/after   : cosine similarity between complaint photo and closure photo embeddings

Thresholds below are hand-set and get calibrated on the shared benchmark later.
"""
from typing import Protocol

import numpy as np
from PIL import Image

PROMPTS = {  # category -> (problem present, problem fixed)
    "pothole": ("a pothole on a road", "a smooth intact road"),
    "garbage": ("a pile of garbage on the street", "a clean street"),
    "streetlight": ("a broken or dark street light", "a working lit street light"),
    "drain": ("a blocked overflowing drain", "a clean clear drain"),
    "water_leak": ("water leaking on the road", "a dry road"),
}
SCENE_STILL_BROKEN = 0.65     # P(problem present) at or above this -> closure photo still shows the problem
DIFFERENT_PLACE = 0.55        # complaint vs closure embedding cosine below this -> probably a different place
LR_SCENE_BROKEN, LR_DIFFERENT_PLACE = 5.0, 3.0


class Embedder(Protocol):
    def image(self, img: Image.Image) -> np.ndarray: ...
    def text(self, texts: list[str]) -> np.ndarray: ...


class OpenClipEmbedder:
    def __init__(self, model: str = "ViT-B-32", pretrained: str = "laion2b_s34b_b79k"):
        import open_clip
        import torch
        self._torch = torch
        self.model, _, self.preprocess = open_clip.create_model_and_transforms(model, pretrained=pretrained)
        self.tokenizer = open_clip.get_tokenizer(model)
        self.model.eval()

    def image(self, img: Image.Image) -> np.ndarray:
        with self._torch.no_grad():
            v = self.model.encode_image(self.preprocess(img.convert("RGB")).unsqueeze(0))
        return _unit(v[0].numpy())

    def text(self, texts: list[str]) -> np.ndarray:
        with self._torch.no_grad():
            v = self.model.encode_text(self.tokenizer(texts))
        return np.stack([_unit(x.numpy()) for x in v])


_default: Embedder | None = None


def default_embedder() -> Embedder:
    global _default
    if _default is None:
        _default = OpenClipEmbedder()
    return _default


def _unit(v: np.ndarray) -> np.ndarray:
    return v / (np.linalg.norm(v) or 1.0)


def scene_problem_prob(emb: Embedder, img: Image.Image, category: str) -> float | None:
    if category not in PROMPTS:
        return None
    t = emb.text([f"a photo of {p}" for p in PROMPTS[category]])
    logits = 100.0 * t @ emb.image(img)          # CLIP logit scale
    e = np.exp(logits - logits.max())
    return float(e[0] / e.sum())


def clip_checks(closure: Image.Image, category: str, complaint: Image.Image | None = None,
                emb: Embedder | None = None) -> tuple[list[str], list[str], dict]:
    """Return (flags, passed, details) in the same vocabulary as photo.verify_photo."""
    emb = emb or default_embedder()
    flags: list[str] = []
    passed: list[str] = []
    details: dict = {}
    p = scene_problem_prob(emb, closure, category)
    if p is not None:
        details["scene"] = {"p_problem_present": round(p, 3)}
        (flags if p >= SCENE_STILL_BROKEN else passed).append("scene")
    if complaint is not None:
        sim = float(emb.image(closure) @ emb.image(complaint))
        details["before_after"] = {"cosine": round(sim, 3)}
        (flags if sim < DIFFERENT_PLACE else passed).append("before_after")
    return flags, passed, details
