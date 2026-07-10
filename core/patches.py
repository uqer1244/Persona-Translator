import sys
import os

def apply_patches():
    print("[PATCH] Applying mlx_vlm runtime patches...")

    # 1. Patch Gemma4UnifiedProcessor.__init__ signature in mlx_vlm
    try:
        import mlx_vlm.models.gemma4_unified.processing_gemma4_unified as gp
        
        original_gp_init = gp.Gemma4UnifiedProcessor.__init__
        
        def patched_gp_init(self, image_processor=None, tokenizer=None, video_processor=None, **kwargs):
            if video_processor is not None:
                kwargs["video_processor"] = video_processor
            original_gp_init(self, image_processor=image_processor, tokenizer=tokenizer, **kwargs)
            
        gp.Gemma4UnifiedProcessor.__init__ = patched_gp_init
        print("[PATCH] Successfully patched Gemma4UnifiedProcessor.__init__ signature.")
    except Exception as e:
        print(f"[PATCH WARNING] Failed to patch Gemma4UnifiedProcessor.__init__: {e}")

    # 2. Patch gemma4 Model.sanitize in mlx_vlm to conditionally transpose conv weights
    try:
        import mlx_vlm.models.gemma4.gemma4 as g4
        
        def patched_g4_sanitize(self, weights):
            use_clipped = getattr(self.config.vision_config, "use_clipped_linears", False)
            sanitized = {}
            for k, v in weights.items():
                if any(s in k for s in ["input_max", "input_min", "output_max", "output_min"]):
                    if "vision_tower" in k and not use_clipped:
                        continue
                    if "vision_tower" not in k and "audio_tower" not in k:
                        continue
                if "rotary_emb.inv_freq" in k or "rotary_emb" in k:
                    continue
                if self.audio_tower is None and ("audio_tower" in k or "embed_audio" in k):
                    continue

                if k.startswith("model."):
                    new_key = k[len("model.") :]
                else:
                    new_key = k

                if new_key.startswith("language_model.") and not new_key.startswith("language_model.model."):
                    rest = new_key[len("language_model.") :]
                    new_key = "language_model.model." + rest

                # Conv2d: PyTorch [out, in, kH, kW] -> MLX [out, kH, kW, in]
                if (
                    "subsample_conv_projection" in new_key
                    and "conv.weight" in new_key
                    and v.ndim == 4
                ):
                    if v.shape[1] == 3 and v.shape[2] == 3:
                        pass
                    else:
                        v = v.transpose(0, 2, 3, 1)
                
                # Conv1d: PyTorch [out, in, kW] -> MLX [out, kW, in]
                if "depthwise_conv1d.weight" in new_key and v.ndim == 3:
                    if v.shape[1] == 5:
                        pass
                    else:
                        v = v.transpose(0, 2, 1)

                if new_key.endswith(".experts.down_proj"):
                    new_key = new_key.replace(".experts.down_proj", ".experts.switch_glu.down_proj.weight")
                if new_key.endswith(".experts.gate_up_proj"):
                    gate_key = new_key.replace(".experts.gate_up_proj", ".experts.switch_glu.gate_proj.weight")
                    up_key = new_key.replace(".experts.gate_up_proj", ".experts.switch_glu.up_proj.weight")

                    v = v.swapaxes(-1, -2)
                    mid_dim = v.shape[-1] // 2
                    sanitized[gate_key] = v[..., :mid_dim].swapaxes(-1, -2)
                    sanitized[up_key] = v[..., mid_dim:].swapaxes(-1, -2)
                    continue

                sanitized[new_key] = v
            return sanitized

        g4.Model.sanitize = patched_g4_sanitize
        print("[PATCH] Successfully patched gemma4.Model.sanitize weight transposition.")
    except Exception as e:
        print(f"[PATCH WARNING] Failed to patch gemma4.Model.sanitize: {e}")

# Automatically apply patches when imported
apply_patches()
