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
class SafeRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        redirected = super().redirect_request(req, fp, code, msg, headers, newurl)
        redirected.remove_header('Authorization')
        return redirected

with urllib.request.build_opener(SafeRedirect()).open(req) as r:
    path.write_bytes(r.read())
assert hashlib.sha256(path.read_bytes()).hexdigest() == 'd0200691d7ddadd0798a55634ee674ceca7156dcd58e35ef056586ceb3750c2c'
os.environ['RETAINED_R2_ZIP'] = str(path)
run = subprocess.run([sys.executable,'-B',str(Path(__file__).with_name('test_reports_policy.py')),'-v'],text=True,capture_output=True)
assert run.returncode == 0, run.stdout+run.stderr
dest = Path(os.environ['RUNNER_TEMP'])/'sanitized-r2'
result = reports_policy.filter_zip(path,dest)
(dest/'report-filter.json').write_text(json.dumps(result,indent=2),encoding='utf8')
(dest/'policy-tests.txt').write_text(run.stdout+run.stderr,encoding='utf8')
from cache_policy_probe import run_probe
run_probe(dest/'cache-policy-probe.json')
# Recover genuine CI log bytes only; generated artifacts were never uploaded.
import io
import zipfile
request = urllib.request.Request('https://api.github.com/repos/johnnynunez/imageio-ffmpeg/actions/runs/38193991446/logs', headers={'Authorization':'Bearer '+os.environ['GH_TOKEN'], 'Accept':'application/vnd.github+json'})
with urllib.request.build_opener(SafeRedirect()).open(request) as response:
    archive = response.read()
entries=[]
with zipfile.ZipFile(io.BytesIO(archive)) as z:
    for info in z.infolist():
        if info.is_dir(): continue
        assert info.filename.endswith('.txt'), info.filename
        raw=z.read(info)
        entries.append({'name':info.filename,'sha256':hashlib.sha256(raw).hexdigest(),'text':raw.decode('utf-8-sig')})
(dest/'native-run-logs.json').write_text(json.dumps({'run_id':38193991446,'recipe':'41c7e53cf670c28f5a89dbe200edf7595d2aa2f6','log_archive_sha256':hashlib.sha256(archive).hexdigest(),'entries':entries},indent=2),encoding='utf8')
combined='\n'.join(e['text'] for e in entries)
assert '5 passed in 1.44s' in combined
assert 'unlisted report member: .pytest_cache/.gitignore' in combined
(dest/'native-log-summary.json').write_text(json.dumps({'run_id':38193991446,'workflow_conclusion':'failure','native_pytest_stdout':'5 passed in 1.44s','artifact_staging_failure':'.pytest_cache/.gitignore was not allowlisted','recovered_from':'actual GitHub CI log ZIP, not generated report artifact','wheel_retained':False,'source_bundle_retained':False,'junit_independently_downloaded':False,'no_native_build_repeated':True},indent=2),encoding='utf8')
reports_policy.stage(dest, Path(os.environ['RUNNER_TEMP'])/'upload-r2')
print(json.dumps(result,indent=2))
