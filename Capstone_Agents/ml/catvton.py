"""CatVTON virtual try-on inference (mask-based, garment-conditioned diffusion inpainting).

Method: Chong et al., "CatVTON: Concatenation Is All You Need for Virtual Try-On with
Diffusion Models" (ICLR 2025). Weights: ``zhengchong/CatVTON`` (CC BY-NC-SA 4.0,
non-commercial) on top of Stable Diffusion 1.5 inpainting. This is a compact
re-implementation of the published inference loop for AURA; it adds no training.

How it works: the person image (with the garment region masked out) and the garment
image are VAE-encoded and *concatenated along the height axis*. A Stable Diffusion
inpainting UNet whose cross-attention is removed and whose self-attention was
fine-tuned by CatVTON then denoises the masked region so it shows the garment,
attending across the concatenation to copy its colour, print and shape. There is
no text prompt and no 3D body or cloth physics: the output is a *generated visual
preview*, not a garment-fit simulation.
"""
from __future__ import annotations

import inspect
import threading
from pathlib import Path
from typing import Callable

import numpy as np
from PIL import Image

ATTENTION_VARIANTS = ("dresscode-16k-512", "vitonhd-16k-512", "mix-48k-1024")


def resize_and_crop(image: Image.Image, size: tuple[int, int]) -> Image.Image:
    """Centre-crop to the target aspect ratio, then resize."""
    w, h = image.size
    target_w, target_h = size
    if w / h < target_w / target_h:
        new_w, new_h = w, w * target_h // target_w
    else:
        new_w, new_h = h * target_w // target_h, h
    box = ((w - new_w) // 2, (h - new_h) // 2, (w + new_w) // 2, (h + new_h) // 2)
    return image.crop(box).resize(size, Image.LANCZOS)


def resize_and_pad(image: Image.Image, size: tuple[int, int], fill=(255, 255, 255)) -> Image.Image:
    """Fit inside the target size and pad with white (garment images)."""
    w, h = image.size
    target_w, target_h = size
    scale = min(target_w / w, target_h / h)
    new_w, new_h = max(1, int(w * scale)), max(1, int(h * scale))
    canvas = Image.new("RGB", size, fill)
    canvas.paste(image.resize((new_w, new_h), Image.LANCZOS), ((target_w - new_w) // 2, (target_h - new_h) // 2))
    return canvas


class CatVTON:
    """Lazily loaded try-on pipeline. One render at a time (guarded by a lock)."""

    def __init__(self, model_dir: Path, device: str = "auto", attention: str = "dresscode-16k-512") -> None:
        if attention not in ATTENTION_VARIANTS:
            raise ValueError(f"Unknown CatVTON attention weights {attention!r}; choose one of {ATTENTION_VARIANTS}.")
        self.attention = attention
        self.model_dir = Path(model_dir)
        self.requested_device = device
        self._lock = threading.Lock()
        self.unet = self.vae = self.scheduler = None
        self.device = None

    # -- availability -------------------------------------------------------------------
    @property
    def unet_path(self) -> Path:
        return self.model_dir / "sd-inpainting" / "unet" / "diffusion_pytorch_model.fp16.safetensors"

    @property
    def attention_path(self) -> Path:
        return self.model_dir / "catvton" / self.attention / "attention" / "model.safetensors"

    @property
    def vae_path(self) -> Path:
        return self.model_dir / "sd-vae-ft-mse" / "diffusion_pytorch_model.safetensors"

    def missing_files(self) -> list[str]:
        required = [self.unet_path, self.attention_path, self.vae_path,
                    self.model_dir / "sd-inpainting" / "scheduler" / "scheduler_config.json"]
        return [str(path.relative_to(self.model_dir)) for path in required if not path.is_file()]

    @property
    def loaded(self) -> bool:
        return self.unet is not None

    # -- loading ------------------------------------------------------------------------
    def _pick_device(self):
        import torch

        if self.requested_device != "auto":
            return torch.device(self.requested_device)
        if torch.backends.mps.is_available():
            return torch.device("mps")
        if torch.cuda.is_available():
            return torch.device("cuda")
        return torch.device("cpu")

    def load(self) -> None:
        if self.loaded:
            return
        missing = self.missing_files()
        if missing:
            raise FileNotFoundError(
                "Try-on model files are missing: " + ", ".join(missing)
                + ". Run `python -m training.download_tryon_models`."
            )
        import torch
        from diffusers import AutoencoderKL, DDIMScheduler, UNet2DConditionModel
        from diffusers.models.attention_processor import AttnProcessor2_0, SlicedAttnProcessor
        from safetensors.torch import load_file

        device = self._pick_device()
        # fp16 UNet on GPU/Metal; the CPU path needs fp32. The VAE stays fp32 (fp16 VAEs can emit NaNs).
        unet_dtype = torch.float16 if device.type in {"mps", "cuda"} else torch.float32
        unet = UNet2DConditionModel.from_pretrained(
            self.model_dir / "sd-inpainting", subfolder="unet", variant="fp16", torch_dtype=unet_dtype,
        )
        processors = {}
        for name in unet.attn_processors:
            # attn1 = self-attention (kept, CatVTON-tuned); attn2 = text cross-attention (removed).
            if not name.endswith("attn1.processor"):
                processors[name] = _SkipAttention()
            elif device.type == "mps":
                # Person+garment concatenation doubles the tokens; full attention needs ~1.2 GB per
                # layer at 384x512, which does not fit beside the chat model on an 8 GB Mac.
                processors[name] = SlicedAttnProcessor(slice_size=2)
            else:
                processors[name] = AttnProcessor2_0()
        unet.set_attn_processor(processors)
        # The checkpoint was saved from a list of every module whose name contains "attn1"
        # (each block plus its 7 sub-modules), so block i is stored under index 8*i.
        blocks = [module for name, module in unet.named_modules() if name.endswith("attn1")]
        state = load_file(str(self.attention_path))
        remapped: dict[str, torch.Tensor] = {}
        for key, tensor in state.items():
            index, rest = key.split(".", 1)
            if int(index) % 8:
                raise RuntimeError(f"Unexpected CatVTON attention key {key!r}.")
            remapped[f"{int(index) // 8}.{rest}"] = tensor
        result = torch.nn.ModuleList(blocks).load_state_dict(remapped, strict=True)
        if len(blocks) != 16 or result.missing_keys or result.unexpected_keys:
            raise RuntimeError("CatVTON attention weights do not match the Stable Diffusion 1.5 UNet.")
        unet.to(device, dtype=unet_dtype).eval()
        vae = AutoencoderKL.from_pretrained(self.model_dir / "sd-vae-ft-mse", torch_dtype=torch.float32).to(device).eval()
        self.scheduler = DDIMScheduler.from_pretrained(self.model_dir / "sd-inpainting", subfolder="scheduler")
        self.unet, self.vae, self.device, self.unet_dtype = unet, vae, device, unet_dtype

    def unload(self) -> None:
        with self._lock:
            self.unet = self.vae = self.scheduler = None
            try:
                import gc
                import torch

                gc.collect()
                if torch.backends.mps.is_available():
                    torch.mps.empty_cache()
            except Exception:  # noqa: BLE001 - best effort
                pass

    # -- inference ----------------------------------------------------------------------
    def _encode(self, image_tensor):
        latent = self.vae.encode(image_tensor.to(self.device, dtype=self.vae.dtype)).latent_dist.sample()
        return latent * self.vae.config.scaling_factor

    def __call__(
        self,
        person: Image.Image,
        garment: Image.Image,
        mask: Image.Image,
        *,
        size: tuple[int, int] = (384, 512),
        steps: int = 30,
        guidance: float = 2.5,
        seed: int = 42,
        progress: Callable[[float], None] | None = None,
    ) -> Image.Image:
        """Return ``person`` (resized to ``size``) wearing ``garment`` inside ``mask``."""
        import torch

        with self._lock:
            self.load()
            width, height = size
            person = resize_and_crop(person.convert("RGB"), size)
            mask = resize_and_crop(mask.convert("L"), size)
            garment = resize_and_pad(garment.convert("RGB"), size)

            def to_tensor(img: Image.Image):
                array = np.asarray(img, dtype=np.float32) / 127.5 - 1.0
                return torch.from_numpy(array).permute(2, 0, 1)[None]

            mask_array = (np.asarray(mask, dtype=np.float32) / 255.0 >= 0.5).astype(np.float32)
            mask_t = torch.from_numpy(mask_array)[None, None].to(self.device)
            person_t = to_tensor(person).to(self.device)
            garment_t = to_tensor(garment).to(self.device)
            generator = torch.Generator(device="cpu").manual_seed(seed)

            with torch.no_grad():
                masked_latent = self._encode(person_t * (mask_t < 0.5))
                garment_latent = self._encode(garment_t)
                mask_latent = torch.nn.functional.interpolate(mask_t, size=masked_latent.shape[-2:], mode="nearest")
                dtype = self.unet_dtype
                masked_latent, garment_latent, mask_latent = (t.to(dtype) for t in (masked_latent, garment_latent, mask_latent))
                cond = torch.cat([masked_latent, garment_latent], dim=-2)
                cond_mask = torch.cat([mask_latent, torch.zeros_like(mask_latent)], dim=-2)
                latents = torch.randn(cond.shape, generator=generator, dtype=torch.float32).to(self.device, dtype)
                self.scheduler.set_timesteps(steps, device=self.device)
                latents = latents * self.scheduler.init_noise_sigma
                use_cfg = guidance > 1.0
                if use_cfg:  # unconditional branch: garment replaced by zeros
                    uncond = torch.cat([masked_latent, torch.zeros_like(garment_latent)], dim=-2)
                    cond = torch.cat([uncond, cond])
                    cond_mask = torch.cat([cond_mask] * 2)
                step_kwargs = {}
                if "eta" in inspect.signature(self.scheduler.step).parameters:
                    step_kwargs["eta"] = 1.0
                timesteps = self.scheduler.timesteps
                conditions = list(zip(cond.chunk(2), cond_mask.chunk(2))) if use_cfg else [(cond, cond_mask)]
                for index, t in enumerate(timesteps):
                    scaled = self.scheduler.scale_model_input(latents, t)
                    # Unconditional and conditional passes run one after another (half the peak memory).
                    noises = [
                        self.unet(torch.cat([scaled, m, c], dim=1), t, encoder_hidden_states=None, return_dict=False)[0]
                        for c, m in conditions
                    ]
                    if use_cfg:
                        uncond_noise, cond_noise = noises
                        noise = uncond_noise + guidance * (cond_noise - uncond_noise)
                    else:
                        noise = noises[0]
                    latents = self.scheduler.step(noise, t, latents, generator=generator, **step_kwargs).prev_sample
                    if progress:
                        progress((index + 1) / len(timesteps))
                person_latent = latents.split(latents.shape[-2] // 2, dim=-2)[0]
                decoded = self.vae.decode(person_latent.float() / self.vae.config.scaling_factor).sample
            array = ((decoded[0].float().clamp(-1, 1) + 1) * 127.5).permute(1, 2, 0).cpu().numpy().astype(np.uint8)
            result = Image.fromarray(array)
            # Keep every pixel outside the mask from the original photo (face, hands, background).
            soft = Image.fromarray((mask_array * 255).astype(np.uint8)).filter(_feather(width))
            return Image.composite(result, person, soft)


def _feather(width: int):
    from PIL import ImageFilter

    return ImageFilter.GaussianBlur(radius=max(1, width // 160))


class _SkipAttention:
    """Attention processor that removes text cross-attention (CatVTON has no text prompt)."""

    def __call__(self, attn, hidden_states, encoder_hidden_states=None, attention_mask=None, temb=None, *args, **kwargs):
        return hidden_states
