"""Stage public test sources only; no .env, device configuration or secret copies."""
import argparse
from pathlib import Path
import shutil

ROOT=Path(__file__).resolve().parents[1]
FOLDERS=('infra/backend','apps/bridge_runtime','apps/tuya-poller','apps/gree-climate',
         'apps/xiaomi-x10','apps/hc_ingest','apps/ha-growatt-poller','apps/ai-server')


def stage(output):
    if output.exists():
        raise ValueError('Refusing to overwrite an existing test source tree')
    if output.parent.resolve()!=Path('/tmp'):
        raise ValueError('Use a new directory directly under /tmp')
    shutil.copytree(ROOT/'scripts/access_runtime/hc-access-20261030-r10',output,
                    ignore=shutil.ignore_patterns('__pycache__'))
    for folder in FOLDERS:
        source=ROOT/folder;target=output/folder
        target.mkdir(parents=True,exist_ok=True)
        for path in source.glob('*.py'):
            shutil.copyfile(path,target/path.name)
        if (source/'tests').exists():
            shutil.copytree(source/'tests',target/'tests',dirs_exist_ok=True,
                            ignore=shutil.ignore_patterns('__pycache__'))
    for path in (ROOT/'scripts').glob('*.py'):
        shutil.copyfile(path,output/'scripts'/path.name)
    return output


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    print(stage(args.output))
