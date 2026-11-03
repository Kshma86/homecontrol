"""HC-44: writable AI state separated from immutable backup archives/settings."""
from contextlib import contextmanager
import fcntl
import os
import json
import stat
import tempfile
from pathlib import Path
from ai_power_coordination import AiPowerCoordinator


class ScopedAiPowerCoordinator(AiPowerCoordinator):
    def __init__(self, root):
        super().__init__(root)
        self.state_root=Path(os.getenv('HC_AI_STATE_DIR', str(Path(root)/'ai-control')))
        self.path=self.state_root/'ai-power-state.json'

    @contextmanager
    def locked(self):
        self.state_root.mkdir(parents=True,exist_ok=True)
        descriptor=os.open(self.state_root/'ai-power-coordination.lock',os.O_RDWR|os.O_CREAT|os.O_NOFOLLOW|os.O_NONBLOCK,0o600)
        with os.fdopen(descriptor,'r+') as handle:
            info=os.fstat(handle.fileno())
            if not stat.S_ISREG(info.st_mode) or info.st_nlink!=1:raise ValueError('Invalid AI state lock')
            if os.geteuid()==0:os.fchown(handle.fileno(),10001,10001)
            fcntl.flock(handle,fcntl.LOCK_EX)
            yield self.read()

    def read(self):
        try:
            descriptor=os.open(self.path,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK)
        except FileNotFoundError:return {'version':1,'generation':None,'intent':None}
        with os.fdopen(descriptor) as stream:
            if not stat.S_ISREG(os.fstat(stream.fileno()).st_mode):raise ValueError('Invalid AI state file')
            raw=stream.read(65537)
        if len(raw)>65536:raise ValueError('AI state is too large')
        value=json.loads(raw)
        if not isinstance(value,dict) or value.get('version')!=1:raise ValueError('Invalid AI state')
        return value

    def save(self,state):
        self.state_root.mkdir(parents=True,exist_ok=True)
        descriptor,temporary=tempfile.mkstemp(prefix='.ai-state-',dir=self.state_root)
        try:
            with os.fdopen(descriptor,'w') as stream:
                if os.geteuid()==0:os.fchown(stream.fileno(),10001,10001)
                os.fchmod(stream.fileno(),0o600)
                json.dump(state,stream);stream.flush();os.fsync(stream.fileno())
            os.replace(temporary,self.path)
        finally:
            if os.path.exists(temporary):os.unlink(temporary)
