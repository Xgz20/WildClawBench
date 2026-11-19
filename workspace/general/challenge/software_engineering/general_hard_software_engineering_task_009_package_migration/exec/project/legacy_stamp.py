from batchstamp.core import run
from batchstamp.cli import main as _main
def main(argv=None):
    import sys
    args=list(sys.argv[1:] if argv is None else argv)
    args=[{'--source':'--input','--settings':'--config'}.get(v,v) for v in args]
    return _main(args)
if __name__=='__main__':raise SystemExit(main())
