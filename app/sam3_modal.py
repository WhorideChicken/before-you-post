"""SAM 3 open weights on Modal: object outlines for private mode, without Meta's API.

The endpoint returns every instance of the text concept; app/meta.py keeps the ones near the attacker's box, the
same way it does for SAM 3.1. Nothing is stored: a photo stays in the container's memory for its few requests.

Deploy (needs access to the gated facebook/sam3 repo, and a Modal secret "before-you-post" with HF_TOKEN and
SAM3_KEY): uvx modal deploy app/sam3_modal.py
CPU by default; SAM3_GPU=T4 (or L4) at deploy time for a GPU, which Modal only allows with a payment method on file.
"""
import os

import modal

app = modal.App("before-you-post-sam3")
weights = modal.Volume.from_name("sam3-weights", create_if_missing=True)
image = (modal.Image.debian_slim(python_version="3.12")
         .pip_install("torch==2.14.1", "torchvision==0.29.1", "transformers==5.21.0", "pillow", "numpy",
                      "fastapi[standard]")
         .env({"HF_HOME": "/weights"}))


@app.cls(gpu=os.environ.get("SAM3_GPU") or None, cpu=4, memory=8192, image=image, volumes={"/weights": weights},
         secrets=[modal.Secret.from_name("before-you-post")], max_containers=3, scaledown_window=300, timeout=300)
@modal.concurrent(max_inputs=8)
class Sam3:
    @modal.enter()
    def load(self):
        import threading

        import torch
        from transformers import Sam3Model, Sam3Processor

        self.device = "cuda" if torch.cuda.is_available() else "cpu"
        self.model = Sam3Model.from_pretrained("facebook/sam3").to(self.device).eval()
        self.processor = Sam3Processor.from_pretrained("facebook/sam3")
        self.lock, self.recent = threading.Lock(), {}
        weights.commit()  # the first start downloads the weights; later starts read them from the volume

    def encode(self, data: bytes):
        """The image encoder is most of the work, and the agent asks about several clues in the same photo at
        once: the first request encodes it, the others wait for it and reuse it."""
        import hashlib
        import io

        import torch
        from PIL import Image

        key = hashlib.sha256(data).hexdigest()
        with self.lock:
            if key not in self.recent:
                img = Image.open(io.BytesIO(data)).convert("RGB")
                inputs = self.processor(images=img, return_tensors="pt").to(self.device)
                with torch.no_grad():
                    embeds = self.model.get_vision_features(pixel_values=inputs.pixel_values)
                self.recent = {**dict(list(self.recent.items())[-3:]),
                               key: (embeds, inputs.get("original_sizes").tolist())}
            return self.recent[key]

    @modal.fastapi_endpoint(method="POST")
    def segment(self, body: dict):
        """body: {"key": SAM3_KEY, "image": base64 PNG or JPEG, "label": "shipping label"}.
        Returns {"instances": [{"box": [x0, y0, x1, y1] in pixels, "score", "mask": base64 PNG}]}."""
        import base64
        import hmac
        import io

        import numpy as np
        import torch
        from fastapi import HTTPException
        from PIL import Image

        if not hmac.compare_digest(str(body.get("key", "")), os.environ["SAM3_KEY"]):
            raise HTTPException(401, "Bad key")
        embeds, sizes = self.encode(base64.b64decode(body["image"]))
        text = self.processor(text=str(body["label"])[:100], return_tensors="pt").to(self.device)
        with torch.no_grad():
            outputs = self.model(vision_embeds=embeds, **text)
        found = self.processor.post_process_instance_segmentation(
            outputs, threshold=0.5, mask_threshold=0.5, target_sizes=sizes)[0]
        instances = []
        for mask, box, score in zip(found["masks"], found["boxes"], found["scores"]):
            buf = io.BytesIO()
            Image.fromarray(mask.cpu().numpy().astype(np.uint8) * 255).convert("1").save(buf, "PNG")
            instances.append({"box": [round(float(v), 1) for v in box], "score": round(float(score), 3),
                              "mask": base64.b64encode(buf.getvalue()).decode()})
        return {"instances": instances}
