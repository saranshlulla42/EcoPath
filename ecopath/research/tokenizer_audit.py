"""CPU-only diagnostics of the saved tokenizer. No base model is loaded."""
import argparse
import importlib.util
import json
from pathlib import Path

from .audit import LEGACY, REPO, RUN
from .contract import digest, read_jsonl, write_new


def inspect(output):
    from transformers import AutoTokenizer
    tokenizer=AutoTokenizer.from_pretrained(REPO/'ecopath/final',local_files_only=True,trust_remote_code=False)
    spec=importlib.util.spec_from_file_location('legacy_training_source',LEGACY/'scripts/train_qlora_colab.py')
    # Extract format_example and its prompt without importing training dependencies.
    import ast
    tree=ast.parse((LEGACY/'scripts/train_qlora_colab.py').read_text())
    nodes=[n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=='format_example']
    ns={'json':json,'Any':object}
    assignment=next(n for n in tree.body if isinstance(n,ast.Assign) and any(isinstance(t,ast.Name) and t.id=='DEFAULT_SYSTEM_PROMPT' for t in n.targets))
    exec(compile(ast.Module(body=[assignment]+nodes,type_ignores=[]),'<legacy format>','exec'),ns)
    rows=read_jsonl(LEGACY/'data/extinction_risk_dataset_gemini_100.jsonl')
    lengths=[len(tokenizer(ns['format_example'](r))['input_ids']) for r in rows]
    from .prompts import ORIGINAL_SYSTEM
    results=read_jsonl(RUN/'eval_results.jsonl')
    diagnostic=[]
    for r in results:
        messages=[{'role':'system','content':ORIGINAL_SYSTEM},{'role':'user','content':r['prompt_user']}]
        text=tokenizer.apply_chat_template(messages,tokenize=False,add_generation_prompt=True)
        old=tokenizer(text)['input_ids']
        corrected=tokenizer(text,add_special_tokens=False)['input_ids']
        direct=tokenizer.apply_chat_template(messages,tokenize=True,add_generation_prompt=True,return_dict=False)
        diagnostic.append({'idx':r['idx'],'scientific_name':r['scientific_name'],
            'saved_tokenizer_default_duplicates_special_tokens':old!=corrected,
            'single_step_matches_explicit_no_specials':direct==corrected,
            'input_tokens_reconstructed':len(direct),
            'base_decoded_text_retokenized_tokens':len(tokenizer.encode(r['base_model_output'],add_special_tokens=False)),
            'adapted_decoded_text_retokenized_tokens':len(tokenizer.encode(r['ft_model_output'],add_special_tokens=False)),
            'note':'Retokenized text lengths are diagnostics, not original generation token measurements.'})
    result={'phase':'original-tokenizer-diagnostic','model_inference_executed':False,
            'saved_tokenizer_chat_template_sha256':digest(tokenizer.chat_template),
            'training_format_uses_native_template':False,'training_role_tokens':['<|system|>','<|end|>','<|user|>','<|assistant|>'],
            'native_role_tokens':['<|im_start|>','<|im_end|>'],
            'training_role_markers_registered_as_special_tokens':{t:t in tokenizer.all_special_tokens for t in ['<|system|>','<|end|>','<|user|>','<|assistant|>']},
            'training_lengths_reconstructed':{'minimum':min(lengths),'maximum':max(lengths),'over_code_default_4096':sum(x>4096 for x in lengths)},
            'recorded_training_sequence_length':'unavailable; 4096 is script default only',
            'rows':diagnostic,'scope':'Saved adapter tokenizer only. Original base tokenizer revision and generation finish reasons were not logged.'}
    write_new(output,result)
    return result


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--out',required=True);a=p.parse_args()
    inspect(a.out)
