import torch, os
from transformers import AutoModelForCausalLM, AutoTokenizer
from peft import PeftModel

base_name = "Qwen/Qwen2.5-7B-Instruct"
adapter_path = "/content/drive/MyDrive/ecopath_afterJudge/extinction_risk/ecopath_gemini100_run1/final"
out_path = "/content/merged_model"
offload_dir = "/content/offload"
os.makedirs(offload_dir, exist_ok=True)

print("1. Loading base model...")
base_model = AutoModelForCausalLM.from_pretrained(
    base_name,
    dtype=torch.float16,        # fixed deprecation warning too
    device_map="auto",
    offload_folder=offload_dir,
    low_cpu_mem_usage=True,
)

print("2. Loading tokenizer and adapter...")
tokenizer = AutoTokenizer.from_pretrained(base_name)

# ← THIS was the missing fix: pass offload_folder here too
model = PeftModel.from_pretrained(
    base_model,
    adapter_path,
    offload_folder=offload_dir,  # <--- KEY FIX
)

print("3. Merging weights...")
model = model.merge_and_unload()

print("4. Saving merged model...")
model.save_pretrained(out_path, safe_serialization=True)
tokenizer.save_pretrained(out_path)
print("Done! ✓")
