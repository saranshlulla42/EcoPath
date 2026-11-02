"""LM Format Enforcer bridge using its public TokenEnforcer interface.

The upstream Transformers integration currently imports a tokenizer class from
a location removed in Transformers 5. This bridge avoids that version coupling.
Anchor decoding preserves leading spaces, as in the upstream integration:
https://github.com/noamgat/lm-format-enforcer/blob/main/lmformatenforcer/integrations/transformers.py
"""
from __future__ import annotations


def tokenizer_data(tokenizer):
    from lmformatenforcer import TokenEnforcerTokenizerData
    vocabulary=tokenizer.get_vocab()
    ids=sorted(set(vocabulary.values()))
    special=set(tokenizer.all_special_ids)
    anchor=tokenizer.encode('0',add_special_tokens=False)[-1]
    anchor_text=tokenizer.decode([anchor],clean_up_tokenization_spaces=False)
    regular=[]
    for token_id in ids:
        if token_id in special:
            continue
        direct=tokenizer.decode([token_id],clean_up_tokenization_spaces=False)
        continuation=tokenizer.decode([anchor,token_id],clean_up_tokenization_spaces=False)[len(anchor_text):]
        regular.append((token_id,continuation,len(continuation)>len(direct)))
    def decode(tokens):
        return tokenizer.decode(tokens,clean_up_tokenization_spaces=False).rstrip('\ufffd')
    return TokenEnforcerTokenizerData(regular,decode,tokenizer.eos_token_id,False,max(ids)+1)


def prefix_allowed_tokens(tokenizer,schema,data=None):
    from lmformatenforcer import JsonSchemaParser,TokenEnforcer
    enforcer=TokenEnforcer(data if data is not None else tokenizer_data(tokenizer),JsonSchemaParser(schema))
    def allowed(batch_id,sent):
        if batch_id != 0:
            raise ValueError('frozen protocol supports batch size one only')
        return enforcer.get_allowed_tokens(sent.tolist()).allowed_tokens
    return allowed
