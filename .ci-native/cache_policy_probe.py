"""Cheap real-pytest regression for report-directory cache leakage."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile


def run_probe(output):
    rows=[]
    with tempfile.TemporaryDirectory(dir=os.environ['RUNNER_TEMP']) as d:
        for label,extra in [('red-original',[]),('green-no-cache',['-p','no:cacheprovider'])]:
            root=Path(d)/label;root.mkdir()
            for name in ('test_reports_policy.py','reports_policy.py','reports-allowlist.json'):
                shutil.copy2(Path(__file__).with_name(name),root/name)
            cmd=[sys.executable,'-I','-B','-m','pytest','test_reports_policy.py','-v',*extra]
            run=subprocess.run(cmd,cwd=root,text=True,capture_output=True)
            assert run.returncode==0,run.stdout+run.stderr
            entries=sorted(p.relative_to(root).as_posix() for p in root.rglob('*') if p.is_file())
            bytecode=[n for n in entries if n.endswith(('.pyc','.pyo'))]
            cache=[n for n in entries if n.startswith('.pytest_cache/')]
            assert not bytecode,bytecode
            assert bool(cache)==(label=='red-original'),(label,entries)
            rows.append({'case':label,'exit':run.returncode,'bytecode':bytecode,'pytest_cache':cache,'stdout':run.stdout,'stderr':run.stderr})
    Path(output).write_text(json.dumps(rows,indent=2),encoding='utf8')
    return rows

if __name__=='__main__': run_probe(sys.argv[1])
