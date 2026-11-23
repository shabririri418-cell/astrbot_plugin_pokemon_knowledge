"""Verify a manually downloaded official ZIP and stream out XML.gz or ZIM.

No network requests and no general archive extraction. The default password is
publicly documented at https://wiki.52poke.com/wiki/神奇宝贝百科:离线归档.
"""
import argparse
import hashlib
from pathlib import Path
import shutil
import subprocess
import zipfile


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('archive', type=Path)
    parser.add_argument('--sha256', required=True)
    parser.add_argument('--suffix', choices=('.xml.gz', '.zim'), required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--password', default='52P0KEW1K1')
    args = parser.parse_args()
    with args.archive.open('rb') as stream:
        digest = hashlib.file_digest(stream, 'sha256').hexdigest()
    if digest != args.sha256.lower():
        raise ValueError('ZIP SHA256 does not match; output was not modified')
    with zipfile.ZipFile(args.archive) as archive:
        members = [item for item in archive.infolist() if not item.is_dir() and item.filename.endswith(args.suffix)]
        if len(members) != 1:
            raise ValueError('Expected exactly one archive member matching the requested suffix')
        member = members[0]
        target = args.output.resolve()
        if target == args.archive.resolve() or target.exists():
            raise FileExistsError('Output must be a new file; existing files are never overwritten')
        target.parent.mkdir(parents=True, exist_ok=True)
        temporary = target.with_name(target.name + '.extracting')
        # GNU tar does not support encrypted ZIPs; Windows tar/libarchive does.
        tar = shutil.which('bsdtar') or shutil.which('tar')
        native = False
        if tar:
            probe = subprocess.run([tar, '--version'], capture_output=True, text=True)
            native = 'bsdtar' in probe.stdout.lower() or 'libarchive' in probe.stdout.lower()
        with temporary.open('xb') as output:
            if native:
                subprocess.run([tar, '--passphrase', args.password, '-xOf', str(args.archive.resolve()), member.filename],
                               stdout=output, check=True)
            else:
                # Portable, but Python's ZipCrypto is slower for the large ZIM.
                with archive.open(member, pwd=args.password.encode('utf8')) as source:
                    shutil.copyfileobj(source, output, 1024 * 1024)
        if temporary.stat().st_size != member.file_size:
            raise ValueError('Incomplete extraction; keep the original archive and retry')
        temporary.replace(target)
        with target.open('rb') as stream:
            print('EXTRACTED', target.name, target.stat().st_size,
                  hashlib.file_digest(stream, 'sha256').hexdigest())


if __name__ == '__main__':
    main()
