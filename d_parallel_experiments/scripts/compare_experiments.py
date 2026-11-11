"""Compare all nine completed runs and summarize raw wall-clock measurements."""
import json
import statistics
from pathlib import Path
root=Path('/data/cs5488/measurements')
records=[]
baseline=None
baseline_inputs=None
baseline_code=None
for mode in ('l1','l4','d4'):
    for repeat in ('r1','r2','r3'):
        prefix='d4stable' if mode=='d4' else mode
        name=f'{prefix}_6h_{repeat}'
        if mode=='l1' and repeat=='r3':
            name='l1_6h_r3_resume'
        timing=json.loads((root/(name+'.json')).read_text())
        proof=json.loads((root/(name+'_evidence.json')).read_text())
        config=json.loads((Path('/data/cs5488/runs')/name/'effective_spark_config.json').read_text())
        assert timing['exit_code']==0 and all(proof['quality_checks'].values()),name
        assert config['spark.sql.shuffle.partitions']=='12',name
        assert config['spark.sql.adaptive.enabled']=='false',name
        key={k:proof[k] for k in ('fingerprints','parquet_multiset_sha256_sum','parquet_rows','parquet_schema')}
        if baseline is None:baseline=key
        assert key==baseline, 'OUTPUT_MISMATCH: '+name
        if mode=='d4':
            assert set(proof['successful_tasks_by_host'])=={'192.168.20.129','192.168.20.131'},name
        env=json.loads((root/(name+'_environment.json')).read_text())
        assert env['cpu_count']==(1 if mode=='l1' else (4 if mode=='l4' else 2)),name
        manifest=json.loads((Path('/data/cs5488/runs')/name/'input_manifest.json').read_text())
        inputs=sorted((f['name'],f['sha256']) for f in manifest['observed_files'])
        code={k:v for k,v in env['source_sha256'].items() if k.startswith('a_data_pipeline/gharchive_a/') or k.endswith('/run_experiment.py')}
        if baseline_inputs is None:baseline_inputs=inputs
        if baseline_code is None:baseline_code=code
        assert inputs==baseline_inputs and len(inputs)==6,name
        assert code==baseline_code,name
        assert config['spark.master']==({'l1':'local[1]','l4':'local[4]','d4':'spark://192.168.20.130:7077'}[mode]),name
        records.append(dict(**timing,application_id=proof['application_id'],events=proof['parquet_rows'],
                            successful_tasks_by_host=proof['successful_tasks_by_host']))
summary={}
for mode in ('L1','L4','D4'):
    values=[r['elapsed_seconds'] for r in records if r['mode']==mode]
    med=statistics.median(values)
    summary[mode]=dict(raw_seconds=values,median_seconds=med,min_seconds=min(values),max_seconds=max(values),
                       events_per_second=records[0]['events']/med)
for value in summary.values():value['speedup_vs_L1']=summary['L1']['median_seconds']/value['median_seconds']
result=dict(passed=True,comparison='full ordered CSV SHA-256 and unordered Parquet row fingerprints including multiplicity',
            records=records,summary=summary)
(root/'six_hour_comparison.json').write_text(json.dumps(result,indent=2)+'\n')
print(json.dumps(summary,indent=2))
