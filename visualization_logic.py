# core_logic.py
from transformers import AutoConfig, AutoTokenizer, AutoModelForCausalLM, AutoModelForSeq2SeqLM
from huggingface_hub import HfApi
from bertviz import head_view, model_view
import torch
from dotenv import load_dotenv
import gc

load_dotenv()
import os
HF_TOKEN = os.getenv("HF_TOKEN")

MODEL_CACHE = {
    "name": None,
    "model": None,
    "tokenizer": None,
    "config": None
}

if torch.cuda.is_available():
    DEVICE = "cuda"
    print("🚀 Using GPU (CUDA)")
elif torch.backends.mps.is_available():
    DEVICE = "mps"
    print("🚀 Using GPU (Apple Metal)")
else:
    DEVICE = "cpu"
    print("🐢 Using CPU")

def free_memory():
    global MODEL_CACHE
    print("🧹 Cleaning up memory...")
    if MODEL_CACHE["model"] is not None:
        # Move to CPU before deleting to help clear VRAM
        MODEL_CACHE["model"].to("cpu") 
        del MODEL_CACHE["model"]
        del MODEL_CACHE["tokenizer"]
        del MODEL_CACHE["config"]
        
    MODEL_CACHE = {
        "name": None, "model": None, "tokenizer": None, "config": None
    }
    
    gc.collect()
    if torch.cuda.is_available():
        torch.cuda.empty_cache()
    print("✨ RAM/VRAM is clean.")

def load_model_smart(model_name):
    """
    Loads a model ONLY if it's not already currently loaded.
    """
    global MODEL_CACHE
    
    # 1. Cache Hit: Return existing model
    if MODEL_CACHE["name"] == model_name and MODEL_CACHE["model"] is not None:
        print(f"⚡ Cache Hit: Reuse {model_name}")
        return MODEL_CACHE["model"], MODEL_CACHE["tokenizer"], MODEL_CACHE["config"]

    # 2. Cache Miss: Free old memory first
    print(f"🔄 Cache Miss: Switching from {MODEL_CACHE['name']} to {model_name}")
    free_memory()

    # 3. Load New Model (Standard Logic)
    print(f"📥 Loading {model_name} into RAM...")
    config = AutoConfig.from_pretrained(model_name, token=HF_TOKEN)
    tokenizer = AutoTokenizer.from_pretrained(model_name, token=HF_TOKEN)
    
    if config.is_encoder_decoder:
        model = AutoModelForSeq2SeqLM.from_pretrained(model_name, output_attentions=True, token=HF_TOKEN)
    else:
        model = AutoModelForCausalLM.from_pretrained(model_name, output_attentions=True, token=HF_TOKEN)

    model.to(DEVICE)

    # 4. Update Cache
    MODEL_CACHE["name"] = model_name
    MODEL_CACHE["model"] = model
    MODEL_CACHE["tokenizer"] = tokenizer
    MODEL_CACHE["config"] = config
    
    return model, tokenizer, config

def move_to_cpu(tensors):
    if isinstance(tensors, tuple):
        return tuple(t.cpu() for t in tensors)
    return tensors.cpu()

# --- 1. THE SAFETY RAIL ---
def check_model_size(model_name_string, limit_gb=6.0): # Bumped to 6GB
    api = HfApi()
    try:
        info = api.model_info(model_name_string, files_metadata=True)
        size_in_bytes = 0
        has_safetensors = any(f.rfilename.endswith(".safetensors") for f in info.siblings)
        
        for file in info.siblings:
            file_size = file.size if file.size is not None else 0
            if has_safetensors:
                if file.rfilename.endswith(".safetensors"):
                    size_in_bytes += file_size
            elif file.rfilename.endswith(".bin"):
                size_in_bytes += file_size
                
        size_in_gb = size_in_bytes / (1024 ** 3)
        
        # Allow small errors (like 0.0GB) to pass if you want, or block them.
        if size_in_gb > limit_gb:
            return False, f"Model is {size_in_gb:.2f} GB (Limit: {limit_gb} GB)"
            
        return True, f"Model is {size_in_gb:.2f} GB"

    except Exception as e:
        return False, f"Error checking size: {str(e)}"


def get_viz_data(model_name, text_input, view_type="head"):
    # A. Check Size (Only if we are about to load a NEW model)
    if MODEL_CACHE["name"] != model_name:
        # (You need to import/define check_model_size here or above)
        # Assuming check_model_size is defined in your file as discussed previously
        is_safe, msg = check_model_size(model_name) 
        if not is_safe:
            return f"<h1>Error</h1><p>{msg}</p>"

    try:
        # B. Smart Load
        model, tokenizer, config = load_model_smart(model_name)
        
        # C. Truncate
        raw_inputs = tokenizer(text_input, return_tensors='pt', truncation=True, max_length=50)
        # Move inputs to DEVICE
        inputs = {k: v.to(DEVICE) for k, v in raw_inputs.items()}
        
        # D. Run Model
        if config.is_encoder_decoder:
            decoder_input_ids = inputs["input_ids"]
            outputs = model(input_ids=inputs["input_ids"], decoder_input_ids=decoder_input_ids)
            
            tokens = tokenizer.convert_ids_to_tokens(inputs["input_ids"][0])

            encoder_att = move_to_cpu(outputs.encoder_attentions)
            decoder_att = move_to_cpu(outputs.decoder_attentions)
            cross_att = move_to_cpu(outputs.cross_attentions)
            
            if view_type == "model":
                html_obj = model_view(
                    encoder_attention=encoder_att,
                    decoder_attention=decoder_att,
                    cross_attention=cross_att,
                    encoder_tokens=tokens,
                    decoder_tokens=tokens,
                    html_action='return'
                )
            else:
                html_obj = head_view(
                    encoder_attention=encoder_att,
                    decoder_attention=decoder_att,
                    cross_attention=cross_att,
                    encoder_tokens=tokens,
                    decoder_tokens=tokens,
                    html_action='return'
                )
        else:
            outputs = model(**inputs)
            tokens = tokenizer.convert_ids_to_tokens(inputs["input_ids"][0])

            attentions = move_to_cpu(outputs.attentions)
            
            if view_type == "model":
                html_obj = model_view(attention=attentions, tokens=tokens, html_action='return')
            else:
                html_obj = head_view(attention=attentions, tokens=tokens, html_action='return')

        return html_obj.data

    except OSError as ose:
        if "401" in str(e) or "403" in str(e):
            return f"""
            <h1>Access Denied</h1>
            <p>The model <code>{model_name}</code> is gated (requires acceptance of privacy policy).</p>
            <p><strong>Server Admin:</strong> Please ensure the account associated with the <code>HF_TOKEN</code> has accepted the terms for this model on Hugging Face.</p>
            """
        return f"<h1>Error Loading Model</h1><p>{str(e)}</p>"
    except Exception as e:
        return f"<h1>Error Loading Model</h1><p>{str(e)}</p>"