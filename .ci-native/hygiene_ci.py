"""Read and sanitize the historical artifact without modifying its source."""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import urllib.request
import reports_policy

path = Path(os.environ['RUNNER_TEMP'])/'original-r2.zip'
req = urllib.request.Request('https://api.github.com/repos/johnnynunez/imageio-ffmpeg/actions/artifacts/11721620829/zip', headers={'Authorization':'Bearer '+os.environ['GH_TOKEN'], 'Accept':'application/vnd.github+json'})
with urllib.request.urlopen(req) as r:
    path.write_bytes(r.read())
assert hashlib.sha256(path.read_bytes()).hexdigest() == 'd0200691d7ddadd0798a55634ee674ceca7156dcd58e35ef056586ceb3750c2c'
os.environ['RETAINED_R2_ZIP'] = str(path)
run = subprocess.run([sys.executable,'-B',str(Path(__file__).with_name('test_reports_policy.py')),'-v'],text=True,capture_output=True)
assert run.returncode == 0, run.stdout+run.stderr
dest = Path(os.environ['RUNNER_TEMP'])/'sanitized-r2'
result = reports_policy.filter_zip(path,dest)
(dest/'report-filter.json').write_text(json.dumps(result,indent=2),encoding='utf8')
(dest/'policy-tests.txt').write_text(run.stdout+run.stderr,encoding='utf8')
reports_policy.stage(dest, Path(os.environ['RUNNER_TEMP'])/'upload-r2')
print(json.dumps(result,indent=2))
