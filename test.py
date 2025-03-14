import torch
from transformers import AutoModel, AutoProcessor
from transformers.image_utils import load_image

# google/siglip2-so400m-patch16-naflex
# load the model and processor
ckpt = "google/siglip2-base-patch16-naflex"


class SigLIPEmbedder:
    def __init__(self):
        self.model = AutoModel.from_pretrained(ckpt, device_map="auto").eval()
        self.processor = AutoProcessor.from_pretrained(ckpt)

    def encode_text(self, text: list[str]) -> torch.Tensor:
        return self.model.get_text_features(
            **self.processor(text=text, return_tensors="pt").to(self.model.device)
        )

    def encode_image(self, images: list[str]) -> torch.Tensor:
        return self.model.get_image_features(
            **self.processor(images=images, return_tensors="pt").to(self.model.device)
        )

    def calc_similarity(
        self, text_embeds: torch.Tensor, image_embeds: torch.Tensor
    ) -> float:

        # normalized features
        image_embeds = image_embeds / image_embeds.norm(p=2, dim=-1, keepdim=True)
        text_embeds = text_embeds / text_embeds.norm(p=2, dim=-1, keepdim=True)

        # cosine similarity as logits
        logits_per_text = torch.matmul(
            text_embeds, image_embeds.t().to(text_embeds.device)
        )

        logit_scale, logit_bias = self.model.logit_scale.to(
            text_embeds.device
        ), self.model.logit_bias.to(text_embeds.device)
        logits_per_text = logits_per_text * logit_scale.exp() + logit_bias

        logits = logits_per_text.t()[0]
        probs = torch.sigmoid(logits).squeeze(-1)
        scores = probs.tolist()
        if not isinstance(scores, list):
            scores = [scores]
        return scores


labels = [
    "bear looking into the camera",
    "bear looking away from the camera",
    "a bunch of teddy bears",
    "two teddy bears",
    "three teddy bears",
]
images = [
    "https://huggingface.co/datasets/merve/coco/resolve/main/val2017/000000000285.jpg",  # bear
    "https://huggingface.co/datasets/merve/coco/resolve/main/val2017/000000000776.jpg",  # teddy bear
]
images = [load_image(url) for url in images]

if __name__ == "__main__":
    embedder = SigLIPEmbedder()
    text_embeds = embedder.encode_text(labels)
    image_embeds = embedder.encode_image(images)
    print(embedder.calc_similarity(text_embeds, image_embeds))
