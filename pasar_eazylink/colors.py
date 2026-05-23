import os, sys

class C:
    def __init__(self):
        self.enabled = sys.stdout.isatty() and os.getenv('NO_COLOR') is None and os.getenv('TERM','').lower() not in {'','dumb'}
    def _c(self,code,t):
        return f"\033[{code}m{t}\033[0m" if self.enabled else t
    def title(self,t): return self._c('1;36',t)
    def ok(self,t): return self._c('32',t)
    def warn(self,t): return self._c('33',t)
    def err(self,t): return self._c('31',t)

colors=C()
