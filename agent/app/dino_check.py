"""Stretch: DINOv2-small as a second embedding for same-scene matching between the complaint photo and the
closure photo. Plugs into photo.verify_photo next to CLIP; the contract does not change. Imports are lazy and
the embedder is injectable so tests never download the model. Threshold is hand-set, calibrate on the benchmark."""
import numpy as np
from PIL import Image

from . import config

DIFFERENT_SCENE = config.VC["dino"]["different_scene"]   # DINOv2 cosine below this -> probably a different place


class DinoEmbedder:
    def __init__(self, name: str = "facebook/dinov2-small"):
        import torch
        from transformers import AutoImageProcessor, AutoModel
        self._torch = torch
        self.proc = AutoImageProcessor.from_pretrained(name)
        self.model = AutoModel.from_pretrained(name).eval()

    def image(self, img: Image.Image) -> np.ndarray:
        with self._torch.no_grad():
            out = self.model(**self.proc(images=img.convert("RGB"), return_tensors="pt"))
        v = out.last_hidden_state[:, 0][0].numpy()   # CLS token
        return v / (np.linalg.norm(v) or 1.0)


_default = None


def default_embedder():
    global _default
    if _default is None:
        _default = DinoEmbedder()
    return _default


def dino_checks(closure: Image.Image, complaint: Image.Image | None, emb=None) -> tuple[list[str], list[str], dict]:
    if complaint is None:
        return [], [], {}
    emb = emb or default_embedder()
    sim = float(emb.image(closure) @ emb.image(complaint))
    flag = sim < DIFFERENT_SCENE
    return (["same_scene"] if flag else []), ([] if flag else ["same_scene"]), {"same_scene": {"dino_cosine": round(sim, 3)}}
