"""Native minimal RED/GREEN check for the exact MinGW linker flag failure."""
import json
import os
from pathlib import Path
import subprocess
import tempfile

compiler=str(Path(os.environ['TOOLCHAIN'])/'bin/aarch64-w64-mingw32-clang.exe')
with tempfile.TemporaryDirectory(dir=os.environ['RUNNER_TEMP']) as d:
    root=Path(d)
    (root/'probe.c').write_text('int main(void) { return 0; }\n')
    bad=subprocess.run([compiler,'probe.c','-Wl,-Map,probe.map,--trace','-o','bad.exe'],cwd=root,text=True,capture_output=True)
    assert bad.returncode and 'unknown argument: --trace' in bad.stderr, bad.stdout+bad.stderr
    good=subprocess.run([compiler,'probe.c','-Wl,-Map,probe.map,--verbose','-o','good.exe'],cwd=root,text=True,capture_output=True)
    assert good.returncode==0,good.stdout+good.stderr
    assert (root/'probe.map').stat().st_size>0
    executed=subprocess.run([str(root/'good.exe')],timeout=10)
    assert executed.returncode==0
    text=json.dumps({'bad_exit':bad.returncode,'good_exit':good.returncode,'native_execution_exit':executed.returncode},indent=2)+'\nRED\n'+bad.stdout+bad.stderr+'\nGREEN\n'+good.stdout+good.stderr
    (Path(os.environ['REPORTS'])/'runtime-probe.txt').write_text(text,encoding='utf8')
