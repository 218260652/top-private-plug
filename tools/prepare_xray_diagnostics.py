#!/usr/bin/env python3
"""Forward core diagnostics through the pinned library callback."""
import argparse
from pathlib import Path
import subprocess


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--source', type=Path, required=True)
    args = parser.parse_args()
    path = args.source.resolve() / 'libv2ray_main.go'
    value = path.read_text()
    if '// TPP bounded diagnostic callback' in value:
        return
    replacements = [
        ('logger *log.Logger // Standard logger', 'logger *log.Logger // Standard logger\n\tcallback CoreCallbackHandler'),
        ('corecommlog.NewLogger(createStdoutLogWriter())', 'corecommlog.NewLogger(createStdoutLogWriter(s))'),
        ('w.logger.Print(s)\n\treturn nil', '// TPP bounded diagnostic callback; the app redacts credentials before retaining text.\n\tif w.callback != nil {\n\t\tw.callback.OnEmitStatus(100, s)\n\t} else {\n\t\tw.logger.Print(s)\n\t}\n\treturn nil'),
        ('func createStdoutLogWriter() corecommlog.WriterCreator', 'func createStdoutLogWriter(callback CoreCallbackHandler) corecommlog.WriterCreator'),
        ('logger: log.New(os.Stdout, "", 0),', 'logger: log.New(os.Stdout, "", 0),\n\t\t\tcallback: callback,'),
    ]
    for old, new in replacements:
        if value.count(old) != 1:
            raise SystemExit('Unexpected pinned diagnostic source layout: ' + old)
        value = value.replace(old, new)
    path.write_text(value)
    subprocess.run(['gofmt', '-w', str(path)], check=True)


if __name__ == '__main__':
    main()
