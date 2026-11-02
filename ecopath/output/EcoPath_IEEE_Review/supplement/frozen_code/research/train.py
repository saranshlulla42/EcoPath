"""Opt-in, three-seed QLoRA training with assistant-only labels and validation.

This is a new protocol, never a reconstruction of the legacy run. No model or
dependency is downloaded. Populate a vetted local cache before execution.
"""
from __future__ import annotations
import argparse
import json
from pathlib import Path
import re
import time

from .contract import canonical, digest, file_hash, read_jsonl, write_new
from .dataset import validate_examples
from .prompts import ENGINEERED_SYSTEM, messages_for
from backend.evidence_contract import FIELDS, VERSION
from .runner import code_hashes, code_snapshot, environment


def encode_example(tokenizer, example, max_length, prompt_style='full_schema'):
    messages = messages_for(example['payload'],'engineered')
    if prompt_style == 'engineered_compact_schema':
        short_contract=(
            f"\nREPORT STRUCTURE: Return a JSON object with schema_version='{VERSION}', "
            "example_id, scientific_name, draft_for_review='draft_for_human_review', "
            f"fields containing exactly these keys: {', '.join(FIELDS)}. "
            "Each field is {value: string|number|string[]|null, kind: source_reported|unavailable, source_ids: string[]}. "
            "Also include claims: [{text, source_ids}] and suggested_actions: string[]."
        )
        system=ENGINEERED_SYSTEM.replace(
            'conforming to the supplied schema', 'matching the concise report structure below'
        )
        messages[0]['content']=system+short_contract
    elif prompt_style != 'full_schema':
        raise ValueError(f'unknown training prompt style: {prompt_style}')
    prefix = tokenizer.apply_chat_template(messages,tokenize=True,add_generation_prompt=True,return_dict=False)
    full = tokenizer.apply_chat_template(messages+[{'role':'assistant','content':canonical(example['expected'])}],
                                         tokenize=True,add_generation_prompt=False,return_dict=False)
    if full[:len(prefix)] != prefix:
        raise ValueError('chat-template prefix mismatch; assistant masking would be unsafe')
    if len(full) > max_length:
        raise ValueError(f"{example['example_id']}: training example exceeds sequence budget; no silent truncation")
    if len(full) == len(prefix):
        raise ValueError('empty training target')
    return {'input_ids':full,'attention_mask':[1]*len(full),'labels':[-100]*len(prefix)+full[len(prefix):]}


def train(config_path,dataset_path,output,execute=False):
    if not execute:
        raise ValueError('training requires --execute; no paid or remote resource is provisioned')
    cfg=json.loads(Path(config_path).read_text())
    if len(set(cfg['seeds'])) != len(cfg['seeds']):
        raise ValueError('training seeds must be independent and unique')
    if not re.fullmatch('[0-9a-f]{40}',cfg['model']['revision'] or ''):
        raise ValueError('base/tokenizer revision must be an immutable commit')
    examples=validate_examples(read_jsonl(dataset_path))
    if any(e['split'] not in {'train','validation'} for e in examples):
        raise ValueError('training input must contain only train/validation partitions; keep pilot/test references separate')
    train_rows=[e for e in examples if e['split']=='train']
    val_rows=[e for e in examples if e['split']=='validation']
    if not train_rows or not val_rows:
        raise ValueError('training and validation species required')
    root=Path(output)
    root.mkdir(parents=True,exist_ok=True)
    # Exclusive run manifest prevents accidental overwrite/resume across protocols.
    write_new(root/'training_protocol.json',{'config':cfg,'dataset_sha256':file_hash(dataset_path),
              'code_sha256':code_hashes(),'code_snapshot':code_snapshot(),'environment':environment(),
              'selection':'minimum validation loss across epoch checkpoints, separately per seed',
              'labels':'assistant tokens only; no hidden references; no truncation',
              'test_targets_used_for_training_or_selection':False})
    results=[]
    for seed in cfg['seeds']:
        directory=root/f'seed-{seed}'
        directory.mkdir(exist_ok=False)
        started=time.perf_counter()
        result={'seed':seed,'status':'failed','failure':None,'wall_seconds':None,'gpu_hours':None,
                'peak_allocated_bytes':None,'hardware':None,'environment':environment()}
        model=None
        trainer=None
        try:
            import torch
            from datasets import Dataset
            from peft import LoraConfig, TaskType, get_peft_model, prepare_model_for_kbit_training
            from transformers import AutoTokenizer,AutoModelForCausalLM,BitsAndBytesConfig,Trainer,TrainingArguments,set_seed
            if not torch.cuda.is_available():
                raise RuntimeError('QLoRA training requires an available CUDA device')
            set_seed(seed)
            result['hardware']=[torch.cuda.get_device_name(i) for i in range(torch.cuda.device_count())]
            for i in range(torch.cuda.device_count()):
                torch.cuda.reset_peak_memory_stats(i)
            dtype=getattr(torch,cfg['model']['compute_dtype'])
            mc=cfg['model']
            common={'revision':mc['revision'],'local_files_only':True,'trust_remote_code':False}
            tokenizer=AutoTokenizer.from_pretrained(mc['id'],**common)
            if not tokenizer.chat_template:
                raise ValueError('missing model chat template')
            if tokenizer.pad_token_id is None:
                tokenizer.pad_token=tokenizer.eos_token
            model=AutoModelForCausalLM.from_pretrained(mc['id'],**common,device_map={'':torch.cuda.current_device()},
                torch_dtype=dtype,quantization_config=BitsAndBytesConfig(load_in_4bit=True,bnb_4bit_quant_type='nf4',
                     bnb_4bit_use_double_quant=True,bnb_4bit_compute_dtype=dtype))
            if cfg.get('keep_frozen_base_fp16', False):
                # PEFT's default preparation casts every non-quantized base
                # parameter to fp32. Qwen's untied vocabulary embedding and
                # lm_head alone cost about 2 GiB at this vocabulary size.
                # Keep frozen base weights in the requested compute dtype and
                # use non-reentrant checkpointing; trainable LoRA parameters
                # are still prepared by get_peft_model below.
                for param in model.parameters():
                    param.requires_grad = False
                if cfg['gradient_checkpointing']:
                    model.gradient_checkpointing_enable(
                        gradient_checkpointing_kwargs=cfg.get(
                            'gradient_checkpointing_kwargs', {'use_reentrant': False}
                        )
                    )
            else:
                model=prepare_model_for_kbit_training(model,use_gradient_checkpointing=cfg['gradient_checkpointing'])
            model=get_peft_model(model,LoraConfig(r=cfg['lora']['r'],lora_alpha=cfg['lora']['alpha'],
                    lora_dropout=cfg['lora']['dropout'],target_modules=cfg['lora']['target_modules'],bias='none',task_type=TaskType.CAUSAL_LM))
            model.config.use_cache=False
            prompt_style=cfg.get('training_prompt_style','full_schema')
            train_ds=Dataset.from_list([encode_example(tokenizer,e,cfg['max_seq_length'],prompt_style) for e in train_rows])
            val_ds=Dataset.from_list([encode_example(tokenizer,e,cfg['max_seq_length'],prompt_style) for e in val_rows])
            def collate(batch):
                size=max(len(b['input_ids']) for b in batch)
                return {key:torch.tensor([b[key]+[pad]*(size-len(b[key])) for b in batch])
                        for key,pad in [('input_ids',tokenizer.pad_token_id),('attention_mask',0),('labels',-100)]}
            steps_per_epoch=(len(train_rows)+cfg['batch_size']*cfg['gradient_accumulation_steps']-1)//(cfg['batch_size']*cfg['gradient_accumulation_steps'])
            warmup_steps=round(cfg['warmup_ratio']*steps_per_epoch*cfg['epochs'])
            args=TrainingArguments(output_dir=str(directory/'checkpoints'),seed=seed,data_seed=seed,
                per_device_train_batch_size=cfg['batch_size'],per_device_eval_batch_size=cfg['eval_batch_size'],
                gradient_accumulation_steps=cfg['gradient_accumulation_steps'],learning_rate=cfg['learning_rate'],
                num_train_epochs=cfg['epochs'],warmup_steps=warmup_steps,weight_decay=cfg['weight_decay'],
                optim=cfg['optimizer'],lr_scheduler_type=cfg['scheduler'],logging_steps=cfg['logging_steps'],
                eval_strategy='epoch',save_strategy='epoch',load_best_model_at_end=True,metric_for_best_model='eval_loss',
                greater_is_better=False,save_total_limit=cfg['save_total_limit'],report_to='none',
                bf16=mc['compute_dtype']=='bfloat16',fp16=mc['compute_dtype']=='float16',
                gradient_checkpointing=cfg['gradient_checkpointing'],prediction_loss_only=True)
            class AssistantOnlyTrainer(Trainer):
                def compute_loss(self, model, inputs, return_outputs=False, num_items_in_batch=None):
                    batch=dict(inputs)
                    labels=batch.pop('labels')
                    if labels.shape[0] != 1:
                        raise ValueError('assistant-only logits slicing requires batch_size=1')
                    target_positions=torch.nonzero(labels[0] != -100,as_tuple=False).flatten()
                    if target_positions.numel() == 0 or target_positions[0] == 0:
                        raise ValueError('training target must contain assistant tokens after a prompt')
                    prediction_positions=target_positions-1
                    outputs=model(**batch,logits_to_keep=prediction_positions)
                    targets=labels[:,target_positions]
                    logits=outputs.logits.float().reshape(-1,model.config.vocab_size)
                    loss=torch.nn.functional.cross_entropy(logits,targets.reshape(-1))
                    return (loss,outputs) if return_outputs else loss

            trainer=AssistantOnlyTrainer(model=model,args=args,train_dataset=train_ds,eval_dataset=val_ds,data_collator=collate)
            training_start=time.perf_counter()
            trainer.train()
            torch.cuda.synchronize()
            training_seconds=time.perf_counter()-training_start
            trainer.save_model(str(directory/'selected_adapter'))
            tokenizer.save_pretrained(directory/'selected_adapter')
            write_new(directory/'selected_adapter/adapter_provenance.json',{
                'base_model':mc['id'],'base_revision':mc['revision'],'training_seed':seed,
                'dataset_sha256':file_hash(dataset_path),'code_sha256':code_hashes(),
                'train_validation_species':sorted({e['species_id'] for e in examples}),
                'train_validation_genera':sorted({e['genus'] for e in examples}),
                'selection':'minimum validation loss across epoch checkpoints'})
            trainer.state.save_to_json(str(directory/'trainer_state.json'))
            result.update(status='completed',training_seconds=training_seconds,gpu_hours=training_seconds/3600,
                gpu_hours_scope='single GPU, Trainer.train wall time including checkpointing and validation; excludes loading/preprocessing',
                best_model_checkpoint=trainer.state.best_model_checkpoint,best_validation_loss=trainer.state.best_metric,
                peak_allocated_bytes={str(i):torch.cuda.max_memory_allocated(i) for i in range(torch.cuda.device_count())},
                memory_scope='peak allocated tensor memory since before model loading; does not include all driver allocations',
                chat_template_sha256=digest(tokenizer.chat_template))
        except Exception as exc:
            result['failure']=f'{type(exc).__name__}: {exc}'
        finally:
            result['wall_seconds']=time.perf_counter()-started
            write_new(directory/'training_result.json',result)
            results.append(result)
            if model is not None:
                if trainer is not None:
                    del trainer
                del model
                torch.cuda.empty_cache()
    write_new(root/'training_results.json',results)
    return results


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--config',required=True);p.add_argument('--dataset',required=True);p.add_argument('--out',required=True)
    p.add_argument('--execute',action='store_true')
    a=p.parse_args()
    print(json.dumps(train(a.config,a.dataset,a.out,a.execute),indent=2))
