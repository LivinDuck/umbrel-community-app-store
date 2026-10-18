from pathlib import Path
import tarfile
root=Path(__file__).resolve().parent
with tarfile.open(root/'public/source.tar.gz','w:gz') as archive:
    for p in sorted(root.rglob('*')):
        if not p.is_file() or 'node_modules' in p.parts or p.name in {'credentials.json','source.tar.gz'}:
            continue
        archive.add(p,arcname=str(p.relative_to(root)))
