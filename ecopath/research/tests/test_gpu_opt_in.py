"""Live model smoke check; cached weights and explicit opt-in are mandatory."""
import json
import os
from pathlib import Path

import pytest


@pytest.mark.skipif(not os.environ.get('ECOPATH_GPU_CONFIG'),reason='opt-in GPU/model test; no model inference in routine tests')
def test_cached_model_schema_generation():
    import torch
    from research.dataset import make_variant
    from research.fixtures import records
    from research.prompts import messages_for
    from research.runner import HFBackend
    from research.contract import report_errors,strict_json
    if not torch.cuda.is_available():
        pytest.skip('CUDA unavailable')
    config=json.loads(Path(os.environ['ECOPATH_GPU_CONFIG']).read_text())
    method=next(m for m in config['methods'] if m['method']=='constrained')
    example=make_variant(records(1)[0],'complete','pilot',42,.5)
    backend=HFBackend(config,method)
    try:
        result=backend.generate(messages_for(example['payload'],'constrained'))
        assert not result['truncated']
        assert not report_errors(strict_json(result['raw']),example['payload'])
    finally:backend.close()
