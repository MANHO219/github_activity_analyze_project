"""Compare a source-file slice of Python event Parquet with a complete Spark run.

Uses disk-backed exact rows and daily keys/counts; does not run Spark or Python
cleaning. Full-day deduplication can change source provenance across the slice
boundary: report any difference rather than silently discarding provenance fields.
"""
import argparse
import csv
import hashlib
import json
import sqlite3
from collections import Counter
from datetime import date, datetime
from pathlib import Path

import pyarrow as pa
import pyarrow.dataset as ds

COLUMNS = ['event_id', 'event_type', 'event_time', 'repo_id', 'repo_name',
           'actor_id', 'actor_login', 'event_date', 'source_file', 'source_line',
           'source_hour', 'time_outside_file_hour', 'optional_field_issues']


def digest(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def canonical(row):
    def value(v):
        if isinstance(v, (datetime, date)):
            return v.isoformat()
        return v
    return json.dumps({k: value(row[k]) for k in COLUMNS},
                      ensure_ascii=False, separators=(',', ':'), sort_keys=True)


def run(args):
    out = Path(args.output)
    out.mkdir(parents=True, exist_ok=False)
    report = {'passed': False, 'status': 'running',
              'comparison': 'exact full event values and daily key/count sets',
              'scope': args.source_files,
              'scope_basis': 'source_file, not event_time',
              'boundary_note': 'Full-day deduplication may select a different source occurrence across the six-hour boundary; provenance fields remain part of the comparison.',
              'inputs': {}, 'checks': {}}
    db = sqlite3.connect(out / 'comparison.sqlite3')
    try:
        schemas = {}
        for side, path in [('python', args.python_parquet), ('spark', args.spark_parquet)]:
            dataset = ds.dataset(path, format='parquet')
            schemas[side] = dataset.schema
            if dataset.schema.names != COLUMNS:
                raise ValueError(f'{side}: unexpected fields {dataset.schema.names}')
            for key in ['event_time', 'source_hour']:
                if dataset.schema.field(key).type != pa.timestamp('us', tz='UTC'):
                    raise ValueError(f'{side}: invalid timestamp type {key}')
            report['inputs'][side] = {
                'path': str(Path(path).resolve()),
                'files': [{'path': str(p), 'bytes': p.stat().st_size, 'sha256': digest(p)}
                          for p in sorted(Path(f) for f in dataset.files)],
                'schema': str(dataset.schema),
                'total_parquet_rows': dataset.count_rows(),
            }
            db.execute(f'CREATE TABLE {side} (id TEXT, row TEXT, repo TEXT, day TEXT, type TEXT)')
            sources = Counter()
            filt = ds.field('source_file').isin(args.source_files) if side == 'python' else None
            for batch in dataset.to_batches(filter=filt, batch_size=10000):
                rows = batch.to_pylist()
                sources.update(row['source_file'] for row in rows)
                db.executemany(f'INSERT INTO {side} VALUES (?,?,?,?,?)',
                               [(str(row['event_id']), canonical(row), str(row['repo_id']),
                                 row['event_date'].isoformat(), row['event_type']) for row in rows])
            db.execute(f'CREATE INDEX {side}_id ON {side}(id)')
            db.execute(f'CREATE TABLE {side}_daily AS SELECT repo,day,type,COUNT(*) AS n FROM {side} GROUP BY repo,day,type')
            n, unique = db.execute(f'SELECT COUNT(*),COUNT(DISTINCT id) FROM {side}').fetchone()
            report['inputs'][side].update(selected_rows=n, distinct_event_ids=unique,
                                           selected_source_counts=dict(sources))
            report['checks'][side+'_ids_unique'] = n == unique
            report['checks'][side+'_expected_rows'] = n == args.expected_rows
            report['checks'][side+'_source_scope'] = set(sources) == set(args.source_files)
        report['checks']['field_types_equal'] = all(
            schemas['python'].field(k).type.equals(schemas['spark'].field(k).type) for k in COLUMNS)
        db.execute('CREATE TABLE exported_daily (repo TEXT,day TEXT,type TEXT,n INTEGER)')
        daily = Path(args.spark_daily)
        with daily.open(encoding='utf-8', newline='') as stream:
            reader = csv.DictReader(stream)
            if reader.fieldnames != ['repo_id', 'event_date', 'event_type', 'event_count']:
                raise ValueError('Unexpected Spark daily columns')
            db.executemany('INSERT INTO exported_daily VALUES (?,?,?,?)',
                           ((r['repo_id'], r['event_date'], r['event_type'], int(r['event_count'])) for r in reader))
        report['inputs']['spark_daily'] = {'path': str(daily.resolve()), 'sha256': digest(daily)}
        n = db.execute('SELECT COUNT(*) FROM exported_daily').fetchone()[0]
        unique = db.execute('SELECT COUNT(*) FROM (SELECT DISTINCT repo,day,type FROM exported_daily)').fetchone()[0]
        report['checks']['spark_daily_keys_unique'] = n == unique
        report['daily_groups'] = {side: db.execute(f'SELECT COUNT(*) FROM {side}').fetchone()[0]
                                  for side in ['python_daily', 'spark_daily', 'exported_daily']}
        report['differences'] = {}
        pairs = [('event_ids', 'id', 'python', 'spark'),
                 ('event_fields', 'row', 'python', 'spark'),
                 ('daily_keys', 'repo,day,type', 'python_daily', 'exported_daily'),
                 ('daily_counts', 'repo,day,type,n', 'python_daily', 'exported_daily'),
                 ('spark_daily_internal', 'repo,day,type,n', 'spark_daily', 'exported_daily')]
        for label, cols, a, b in pairs:
            for suffix, left, right in [('left_only', a, b), ('right_only', b, a)]:
                query = f'SELECT {cols} FROM {left} EXCEPT SELECT {cols} FROM {right}'
                count = db.execute('SELECT COUNT(*) FROM ('+query+')').fetchone()[0]
                key = label+'_'+suffix
                report['differences'][key] = count
                report['checks'][key+'_zero'] = count == 0
                (out/(key+'_examples.json')).write_text(
                    json.dumps(db.execute(query+' LIMIT 20').fetchall(), ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
        field_counts = Counter()
        if all(report['checks'][s+'_ids_unique'] for s in ['python', 'spark']):
            for a, b in db.execute('SELECT python.row,spark.row FROM python JOIN spark ON python.id=spark.id WHERE python.row<>spark.row'):
                a, b = json.loads(a), json.loads(b)
                field_counts.update(k for k in COLUMNS if a[k] != b[k])
        report['field_mismatch_counts'] = {k: field_counts[k] for k in COLUMNS}
        report['passed'] = all(report['checks'].values())
        report['status'] = 'completed'
        db.commit()
    except Exception as exc:
        report['status'] = 'error'
        report['error'] = f'{type(exc).__name__}: {exc}'
        raise
    finally:
        db.close()
        (out/'comparison_summary.json').write_text(json.dumps(report, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
    return report


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--python-parquet', required=True)
    p.add_argument('--spark-parquet', required=True)
    p.add_argument('--spark-daily', required=True)
    p.add_argument('--output', required=True)
    p.add_argument('--expected-rows', type=int, default=1177282)
    p.add_argument('--source-files', nargs='+', default=[f'2024-01-15-{h}.json.gz' for h in range(6)])
    result = run(p.parse_args())
    print(json.dumps({'passed': result['passed'], 'status': result['status']}))
    raise SystemExit(0 if result['passed'] else 1)
