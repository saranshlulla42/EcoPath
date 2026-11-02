"""Generate static figures only from saved audit/run records."""
import argparse
import json
from pathlib import Path


def plot(audit_dir,out_dir,run_summary=None):
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    from .contract import file_hash,write_new
    source=Path(audit_dir)/'audit.json'
    audit=json.loads(source.read_text())
    out=Path(out_dir);out.mkdir(parents=True,exist_ok=True)
    files=[]
    def save(fig,name):
        for suffix in ('png','svg'):
            path=out/f'{name}.{suffix}'
            if path.exists():raise FileExistsError(path)
            fig.savefig(path,dpi=180,bbox_inches='tight',facecolor='white')
            files.append(path.name)
        plt.close(fig)
    plt.rcParams.update({'font.size':11,'axes.spines.top':False,'axes.spines.right':False})
    fig,ax=plt.subplots(figsize=(8,4.5))
    ax.bar(['Base model','Saved adapted model'],[audit['legacy_metrics'][m]['strict_json_valid'] for m in ('base','adapted')],color=['#8295a3','#296c86'])
    ax.set_ylim(0,17);ax.set_yticks([0,5,10,15]);ax.set_ylabel('Valid JSON outputs (N = 15 each)')
    ax.set_title('Original saved experiment: structural result')
    for x,m in enumerate(('base','adapted')):
        n=audit['legacy_metrics'][m]['strict_json_valid'];ax.text(x,n+.3,f'{n}/15',ha='center')
    fig.text(.5,-.03,'Weak prompt without an explicit schema; taxonomy-only evidence. No fidelity improvement established.',ha='center',fontsize=9)
    save(fig,'original-json')
    fields=['iucn_status','population_trend','population_size','habitat','range_summary','diet','breeding_behavior','migratory_behavior']
    fig,ax=plt.subplots(figsize=(8,5))
    values=[audit['availability'][f] for f in fields]
    ax.barh([f.replace('_',' ') for f in fields],values,color='#296c86')
    ax.set_xlim(0,105);ax.set_xlabel('Records with a nonempty field (N = 100)')
    ax.set_title('Original dataset: no collected ecological values')
    for y,n in enumerate(values):ax.text(n+1,y,f'{n}/100',va='center')
    save(fig,'original-availability')
    state=audit['training_state']['log_history']
    points=[r for r in state if 'loss' in r]
    fig,ax=plt.subplots(figsize=(8,4))
    ax.plot([r['step'] for r in points],[r['loss'] for r in points],marker='o',color='#296c86')
    ax.set_xlabel('Training update');ax.set_ylabel('Logged training loss');ax.set_title('Original saved loss observations (one run)')
    fig.text(.5,-.03,'Training loss is not validation loss, evidence fidelity or proof of convergence.',ha='center',fontsize=9)
    save(fig,'original-training-loss')
    if run_summary:
        records=json.loads(Path(run_summary).read_text())['results']
        selected=[r for r in records if r['level']=='all']
        fig,ax=plt.subplots(figsize=(9,4))
        labels=[r['method_id'] for r in selected]
        values=[r['metrics']['micro']['structured_field_success_e2e']['value'] for r in selected]
        ax.bar(labels,values,color='#296c86');ax.set_ylim(0,1.1);ax.set_ylabel('Structured field success, end to end')
        ax.set_title(' / '.join(sorted({r['phase'] for r in selected}))+' — saved run only')
        save(fig,'saved-run-structured-success')
    write_new(out/'figure_provenance.json',{'phase':'original-record-audit','audit_source':str(source.resolve()),
        'audit_sha256':file_hash(source),'renderer':'matplotlib','files':files,'model_inference_executed':False,
        'optional_run_summary':str(run_summary) if run_summary else None})


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--audit-dir',required=True);p.add_argument('--out',required=True)
    p.add_argument('--run-summary');a=p.parse_args();plot(a.audit_dir,a.out,a.run_summary)
